"""
Core Utilities — Audit logging, domain whitelisting, helpers
==============================================================
"""
import fnmatch
from urllib.parse import urlparse
from django.conf import settings
from .models import AuditLog


def validate_domain_whitelist(url: str, allowed_domains: list) -> bool:
    """
    Check if a URL's domain matches the organization's allowed domains list.
    Returns True if allowed (or if whitelist is empty = all allowed).
    Supports wildcard patterns like "*.example.com".
    """
    if not allowed_domains:
        return True
    if not url:
        return True
    try:
        hostname = urlparse(url).hostname or ''
    except Exception:
        return False
    hostname = hostname.lower()
    for pattern in allowed_domains:
        pattern = pattern.lower().strip()
        if fnmatch.fnmatch(hostname, pattern):
            return True
    return False


def log_audit(request, action: str, resource_type: str, resource_id: str = '', details: dict = None):
    """Create an immutable audit log entry."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    user = request.user if request.user.is_authenticated else None
    # For API key auth, user is an APIKeyUser proxy -- resolve to real user
    if user and not isinstance(user, User):
        try:
            user = User.objects.get(pk=user.id)
        except Exception:
            user = None

    org = getattr(request.user, 'organization', None) if request.user else None
    if not org:
        return

    ip = get_client_ip(request)

    AuditLog.objects.create(
        organization=org,
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def get_client_ip(request):
    """
    Return the real client IP, respecting the NUM_PROXIES setting.
    See middleware._get_ip for full explanation.
    """
    num_proxies = getattr(settings, 'NUM_PROXIES', 0)
    if num_proxies > 0:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ips = [ip.strip() for ip in xff.split(',') if ip.strip()]
        idx = len(ips) - num_proxies
        if idx >= 0:
            return ips[idx]
    return request.META.get('REMOTE_ADDR')
