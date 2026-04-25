"""
Core Middleware
================
Rate limiting, security headers, request logging, organization context.
"""
import json
import logging
import time
import uuid
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger('apps.core')


class RateLimitMiddleware:
    """
    Per-IP rate limiting using the cache backend (works with DatabaseCache).

    Protects:
      /r/<slug>/  — redirect endpoint (public, highest abuse risk)
      /api/       — authenticated API endpoints

    Uses atomic cache.incr() with fixed-window counters.
    Configurable via settings: REDIRECT_RATE_LIMIT, API_RATE_LIMIT, etc.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.redirect_limit = getattr(settings, 'REDIRECT_RATE_LIMIT', 120)
        self.redirect_window = getattr(settings, 'REDIRECT_RATE_WINDOW', 60)
        self.api_limit = getattr(settings, 'API_RATE_LIMIT', 200)
        self.api_window = getattr(settings, 'API_RATE_WINDOW', 60)

    def __call__(self, request):
        ip = self._get_ip(request)

        if request.path.startswith('/r/'):
            if self._is_rate_limited(ip, 'redirect', self.redirect_limit, self.redirect_window):
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Try again later.'},
                    status=429,
                    headers={
                        'Retry-After': str(self.redirect_window),
                        'X-RateLimit-Limit': str(self.redirect_limit),
                    },
                )
        elif request.path.startswith('/api/'):
            if self._is_rate_limited(ip, 'api', self.api_limit, self.api_window):
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Try again later.'},
                    status=429,
                    headers={
                        'Retry-After': str(self.api_window),
                        'X-RateLimit-Limit': str(self.api_limit),
                    },
                )

        return self.get_response(request)

    def _is_rate_limited(self, ip, scope, limit, window):
        cache_key = f"rl:{scope}:{ip}"
        try:
            count = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=window)
            count = 1
        return count > limit

    @staticmethod
    def _get_ip(request):
        """
        Return the real client IP, aware of trusted reverse proxies.

        When NUM_PROXIES > 0 (e.g. AWS ALB = 1), the ALB appends the real
        client IP as the *last* entry in X-Forwarded-For, making it
        impossible for a client to spoof it by pre-setting the header.
        Without NUM_PROXIES, we fall back to REMOTE_ADDR so the rate limiter
        cannot be bypassed by sending a forged X-Forwarded-For header.
        """
        num_proxies = getattr(settings, 'NUM_PROXIES', 0)
        if num_proxies > 0:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ips = [ip.strip() for ip in xff.split(',') if ip.strip()]
            # The rightmost `num_proxies` IPs are added by trusted proxies.
            # The IP just before them is the real client.
            idx = len(ips) - num_proxies
            if idx >= 0:
                return ips[idx]
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class SecurityHeadersMiddleware:
    """
    Add security response headers to every response.
    OWASP recommended defaults for XSS, clickjacking, MIME-sniffing,
    referrer leakage, and HSTS.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(self)'
        response['X-Permitted-Cross-Domain-Policies'] = 'none'
        # Note: Strict-Transport-Security is handled by Django's SecurityMiddleware
        # via SECURE_HSTS_SECONDS / SECURE_HSTS_PRELOAD — do not set it here or
        # we would overwrite it and drop the 'preload' directive.

        # Content-Security-Policy — applied to the main app and API.
        # Skipped for /lp/ (user-controlled HTML) and /pdf/ /video/ (binary content).
        # TEMPORARY: CSP DISABLED for Clerk CAPTCHA debugging
        if not request.path.startswith(('/lp/', '/pdf/', '/video/')):
            # Temporarily comment out CSP to debug CAPTCHA issues
            pass
            # response['Content-Security-Policy'] = (
            #     "default-src 'self'; "
            #     "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://*.clerk.accounts.dev https://*.clerk.dev https://js.stripe.com; "
            #     "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            #     "img-src 'self' data: blob: https:; "
            #     "font-src 'self' data: https://fonts.gstatic.com; "
            #     "connect-src 'self' https: wss:; "
            #     "frame-src 'self' https://*.clerk.accounts.dev https://*.clerk.dev https://js.stripe.com; "
            #     "object-src 'none'; "
            #     "base-uri 'self';"
            # )
        return response


class RequestLoggingMiddleware:
    """
    Emit a structured JSON log line for every API request.

    Fields logged (never includes Authorization headers, passwords, or tokens):
        request_id  – UUID generated per request for log correlation
        method      – HTTP verb
        path        – URL path (no query string to avoid leaking tokens in ?token=)
        status      – HTTP response status code
        latency_ms  – Round-trip processing time in milliseconds
        user_id     – UUID of authenticated user, null for anonymous
        ip          – Client IP address
        timestamp   – ISO-8601 UTC timestamp of request completion
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = self.get_response(request)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        user_id = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)

        logger.info(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
            "user_id": user_id,
            "ip": self._get_ip(request),
            "timestamp": timezone.now().isoformat(),
        }))

        return response

    @staticmethod
    def _get_ip(request) -> str:
        num_proxies = getattr(settings, 'NUM_PROXIES', 0)
        if num_proxies > 0:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ips = [ip.strip() for ip in xff.split(',') if ip.strip()]
            idx = len(ips) - num_proxies
            if idx >= 0:
                return ips[idx]
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class OrganizationMiddleware:
    """Attach organization to request for quick access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.org = None
        # Skip org lookup for public redirect paths — saves a DB query
        if request.path.startswith('/r/'):
            return self.get_response(request)

        if hasattr(request, 'user') and request.user.is_authenticated:
            request.org = getattr(request.user, 'organization', None)

        response = self.get_response(request)
        return response


class Admin2FAMiddleware:
    """Gate all Django admin requests behind 2FA verification."""

    def __init__(self, get_response):
        self.get_response = get_response
        from decouple import config as env_config
        self.admin_url = '/' + env_config('DJANGO_ADMIN_URL', default='admin/')

    def __call__(self, request):
        path = request.path

        if not path.startswith(self.admin_url):
            return self.get_response(request)

        # Skip 2FA pages themselves
        if '/2fa/' in path:
            return self.get_response(request)

        # Skip unauthenticated users (Django admin login handles them)
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        if not request.user.is_staff:
            return self.get_response(request)

        # Already verified this session
        if request.session.get('admin_2fa_verified'):
            return self.get_response(request)

        from django.shortcuts import redirect
        if request.user.is_2fa_enabled:
            return redirect('admin-2fa-verify')
        else:
            return redirect('admin-2fa-setup')
