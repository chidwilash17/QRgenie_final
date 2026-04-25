"""
QR Codes — Redirect Engine View
=================================
Handles /r/<slug>/ — the core scan redirect endpoint.
PERFORMANCE CRITICAL: target <50ms.

Strategy:
  1. Cache lookup (Redis hit = ~1ms)
  2. Evaluate rules (pure Python, no I/O)
  3. IMMEDIATELY return HttpResponseRedirect
  4. Record scan in a daemon thread (zero impact on response time)
"""
import logging
import os
import threading
import json
from urllib.request import urlopen, Request
from urllib.error import URLError
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .services import get_qr_from_cache, evaluate_rules, get_rotation_destination, get_language_destination, get_time_destination, get_pdf_destination, get_video_destination, get_device_destination, get_geofence_destination, has_active_geofence, get_ab_test_destination, has_active_ab_test, get_deep_link_config, has_active_deep_link, has_active_token_redirect, generate_redirect_token, validate_redirect_token, record_token_usage, check_token_redirect_exhausted, has_active_expiry, check_qr_expiry, increment_expiry_scan
from apps.core.utils import get_client_ip

logger = logging.getLogger('apps.qrcodes')


def _append_utm_params(url, qr):
    """Append UTM query params from the QR code to the destination URL (Feature 42).
    Also validates that the URL uses a safe scheme (http/https only)."""
    if not url:
        return '/'
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
    parsed = urlparse(url)
    # Block dangerous schemes: javascript:, data:, vbscript:, file:, etc.
    if parsed.scheme.lower() not in ('http', 'https'):
        return '/'
    if not any([qr.utm_source, qr.utm_medium, qr.utm_campaign]):
        return url
    params = parse_qs(parsed.query, keep_blank_values=True)
    if qr.utm_source and 'utm_source' not in params:
        params['utm_source'] = [qr.utm_source]
    if qr.utm_medium and 'utm_medium' not in params:
        params['utm_medium'] = [qr.utm_medium]
    if qr.utm_campaign and 'utm_campaign' not in params:
        params['utm_campaign'] = [qr.utm_campaign]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _fast_geoip_lookup(ip: str) -> tuple[str, str, str]:
    """
    Resolve IP → (country, region, city) for language geo-fallback.

    Strategy:
      1. Check in-memory cache first (avoids repeated lookups for same IP)
      2. Try local MaxMind GeoLite2 DB file (~1-2ms)
      3. Fallback: free ip-api.com HTTP API (~50-100ms, 45 req/min limit)
         Cached for 1 hour to stay well within limits.

    Returns e.g. ("IN", "AP", "Visakhapatnam") for Vizag, India.
    Returns ("", "", "") if all methods fail.
    """
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        logger.info(f"[GeoIP] Skipping localhost IP: {ip}")
        return ('', '', '')

    # ── Cache check ──
    cache_key = f"geoip:{ip}"
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"[GeoIP] Cache hit for {ip}: country={cached[0]}, region={cached[1]}, city={cached[2]}")
        return tuple(cached)

    # ── Method 1: Local MaxMind DB ──
    try:
        geoip_path = getattr(settings, 'GEOIP_DB_PATH', '')
        if geoip_path and os.path.isfile(geoip_path):
            import geoip2.database
            with geoip2.database.Reader(geoip_path) as reader:
                geo = reader.city(ip)
                country = geo.country.iso_code or ''
                region = ''
                city = ''
                if geo.subdivisions and geo.subdivisions.most_specific:
                    region = geo.subdivisions.most_specific.iso_code or ''
                if geo.city:
                    city = geo.city.name or ''
                logger.info(f"[GeoIP] MaxMind DB: {ip} → country={country}, region={region}, city={city}")
                result = (country, region, city)
                cache.set(cache_key, list(result), timeout=3600)
                return result
        else:
            logger.info(f"[GeoIP] No MaxMind DB at: {geoip_path or '(not configured)'}")
    except Exception as e:
        logger.warning(f"[GeoIP] MaxMind DB error for {ip}: {e}")

    # ── Method 2: ipinfo.io (HTTPS, free 50k/mo, whitelisted on PythonAnywhere) ──
    try:
        url = f"https://ipinfo.io/{ip}/json"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        country = data.get('country', '')
        region = data.get('region', '')
        city = data.get('city', '')
        if country:
            logger.info(f"[GeoIP] ipinfo.io: {ip} → country={country}, region={region}, city={city}")
            result = (country, region, city)
            cache.set(cache_key, list(result), timeout=3600)
            return result
        else:
            logger.warning(f"[GeoIP] ipinfo.io returned empty country for {ip}: {data}")
    except (URLError, TimeoutError, Exception) as e:
        logger.warning(f"[GeoIP] ipinfo.io failed for {ip}: {e}")

    # ── Method 3: ipapi.co fallback (HTTPS, 1000/day free) ──
    try:
        url = f"https://ipapi.co/{ip}/json/"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0'})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            country = data.get('country_code', '')
            region = data.get('region_code', '')
            city = data.get('city', '')
            if country:
                logger.info(f"[GeoIP] ipapi.co: {ip} → country={country}, region={region}, city={city}")
                result = (country, region, city)
                cache.set(cache_key, list(result), timeout=3600)
                return result
            else:
                logger.warning(f"[GeoIP] ipapi.co returned empty country for {ip}: {data}")
    except (URLError, TimeoutError, Exception) as e:
        logger.warning(f"[GeoIP] ipapi.co failed for {ip}: {e}")

    logger.warning(f"[GeoIP] All methods failed for {ip} — returning empty")
    return ('', '', '')


class RedirectView(View):
    """
    GET /r/<slug>/
    The fastest path in the entire platform. Every millisecond counts.
    """

    def get(self, request, slug):
        # 1. Lookup QR from cache/DB — Redis hit is ~1ms
        qr = get_qr_from_cache(slug)
        if not qr:
            return JsonResponse({'error': 'QR code not found.'}, status=404)

        # 2. Check active status — pure in-memory checks, no I/O
        if qr.status == 'paused':
            return JsonResponse({'error': 'This QR code is currently paused.'}, status=403)

        if qr.status == 'archived':
            return JsonResponse({'error': 'This QR code is no longer active.'}, status=410)

        # 3. Check expiry
        if qr.is_expired():
            # Update status in background, don't block
            threading.Thread(
                target=self._expire_qr, args=(qr.id,), daemon=True,
            ).start()
            return JsonResponse({'error': 'This QR code has expired.'}, status=410)

        # 3b. Check Feature 21 — Expiry-Based QR
        if has_active_expiry(qr):
            expiry_result = check_qr_expiry(qr)
            if expiry_result.get('expired'):
                redirect_url = expiry_result.get('redirect_url', '')
                if redirect_url:
                    logger.info(f"[Expiry] slug={slug} → expired, redirecting to {redirect_url}")
                    return HttpResponseRedirect(redirect_url)
                reason = expiry_result.get('reason', 'expired')
                logger.info(f"[Expiry] slug={slug} → expired: {reason}")
                return render(request, 'qrcodes/token_expired.html', {
                    'reason': reason,
                    'slug': slug,
                })

        # 4. Check password protection
        if qr.is_password_protected:
            return JsonResponse({
                'password_required': True,
                'qr_id': str(qr.id),
                'verify_url': f'/api/v1/qr/{qr.id}/verify-password/',
            }, status=401)

        # ── Pre-compute shared request data ──
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        client_ip = get_client_ip(request)
        accept_lang_header = request.META.get('HTTP_ACCEPT_LANGUAGE', '')

        logger.info(f"[Scan] slug={slug} ip={client_ip} accept_lang={accept_lang_header[:60]}")

        # GeoIP country + region — resolved synchronously.
        country, region, city = _fast_geoip_lookup(client_ip)
        logger.info(f"[Scan] slug={slug} GeoIP → country={country or '(empty)'}, region={region or '(empty)'}, city={city or '(empty)'}")

        # ── Short-Lived Token Redirect (Feature 20) ──
        # If this QR has an active token redirect config, gate access:
        # • No token param → generate a fresh JWT and redirect with ?token=...
        # • Token param present → validate JWT → if valid, proceed; if not, show expired page
        if has_active_token_redirect(qr):
            # ── QR-level exhaustion check (across ALL tokens) ──
            exhaustion = check_token_redirect_exhausted(qr)
            if exhaustion.get('exhausted'):
                reason = exhaustion.get('reason', 'unknown')
                logger.info(f"[TokenRedirect] slug={slug} → QR exhausted: {reason}")
                return render(request, 'qrcodes/token_expired.html', {
                    'reason': reason,
                    'slug': slug,
                })

            token_param = request.GET.get('token')
            if not token_param:
                # Generate a fresh JWT token and redirect
                jwt_token = generate_redirect_token(qr)
                if jwt_token:
                    token_url = f'/r/{slug}/?token={jwt_token}'
                    logger.info(f"[TokenRedirect] slug={slug} → generated token, redirecting")
                    response = HttpResponseRedirect(token_url)
                    # Prevent browser from caching this 302 — each scan MUST
                    # hit the server to get a fresh token.
                    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                    response['Pragma'] = 'no-cache'
                    response['Expires'] = '0'
                    return response
            else:
                # Validate the existing token
                validation = validate_redirect_token(token_param, slug, client_ip)
                if not validation.get('valid'):
                    reason = validation.get('reason', 'unknown')
                    logger.info(f"[TokenRedirect] slug={slug} → token invalid: {reason}")
                    return render(request, 'qrcodes/token_expired.html', {
                        'reason': reason,
                        'slug': slug,
                    })
                # Token is valid — record usage for ALL modes
                payload = validation.get('payload', {})
                record_token_usage(
                    qr_id=payload.get('qr_id', ''),
                    jti=payload.get('jti', ''),
                    client_ip=client_ip,
                )
                logger.info(f"[TokenRedirect] slug={slug} → token valid, proceeding")
                # Fall through to normal redirect logic

        # ── GPS district routing: serve intermediate page ──
        # If this QR has geo_direct district entries configured, serve a lightweight
        # HTML page that asks the browser for cached GPS coordinates (silent if the
        # user has previously allowed location), then POSTs to /resolve-location/.
        # The fallback_url is computed via normal IP routing so if GPS is denied
        # the user still lands somewhere sensible.
        lang_route = None
        has_geo_direct = False
        mandatory_location = False
        try:
            lang_route = qr.language_route
            has_geo_direct = (
                lang_route.is_active
                and bool(getattr(lang_route, 'geo_direct', None))
            )
            mandatory_location = bool(getattr(lang_route, 'mandatory_location', False))
        except Exception:
            pass

        if has_geo_direct:
            geo_direct_entries = getattr(lang_route, 'geo_direct', []) or []
            has_district_entries = any(
                bool((e.get('district') or '').strip()) for e in geo_direct_entries
            )

            if mandatory_location:
                # ── Mandatory GPS mode ──
                # Check if we already have cached coordinates for this IP.
                from .models import DeviceLocationCache
                cached = None
                try:
                    cached = DeviceLocationCache.objects.get(ip_address=client_ip)
                except DeviceLocationCache.DoesNotExist:
                    pass

                if cached:
                    # Resolve immediately using cached GPS coords — no browser prompt needed.
                    district_gps, state_gps, country_gps = _reverse_geocode_nominatim(cached.latitude, cached.longitude)
                    destination = _match_geo_direct_by_district(lang_route, district_gps)
                    if not destination and state_gps and country_gps:
                        destination = get_language_destination(qr, accept_lang_header, country_gps, state_gps, district_gps)
                    if not destination:
                        destination = get_language_destination(qr, accept_lang_header, country, region, city)
                    if not destination:
                        destination = get_rotation_destination(qr)
                    if not destination:
                        destination = qr.destination_url or qr.fallback_url or ''
                    logger.info(f"[GPS] slug={slug} mandatory cached resolve ip={client_ip} → {destination[:80]}")
                    return HttpResponseRedirect(_append_utm_params(destination, qr))

                # No cache: serve GPS page in mandatory mode (no fallback, user must allow)
                resolve_url = request.build_absolute_uri(f'/r/{slug}/resolve-location/')
                logger.info(f"[GPS] slug={slug} mandatory GPS page (no cache for {client_ip})")
                return render(request, 'qrcodes/gps_redirect.html', {
                    'resolve_url': resolve_url,
                    'fallback_url': qr.destination_url or qr.fallback_url or '/',
                    'mandatory': True,
                })

            elif has_district_entries:
                # ── Optional GPS mode (district entries present) ──
                # Compute IP-based fallback for graceful degradation if GPS is denied.
                fallback = get_language_destination(qr, accept_lang_header, country, region, city)
                if not fallback:
                    fallback = get_rotation_destination(qr)
                if not fallback:
                    ua_lower = user_agent.lower()
                    fallback = evaluate_rules(qr, {
                        'device_type': 'mobile' if any(m in ua_lower for m in ['mobile', 'android', 'iphone', 'ipad']) else 'desktop',
                        'country': country,
                        'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    })
                if not fallback:
                    fallback = qr.destination_url or qr.fallback_url or ''

                resolve_url = request.build_absolute_uri(f'/r/{slug}/resolve-location/')
                logger.info(f"[GPS] slug={slug} optional GPS page, fallback={fallback[:80]}")
                return render(request, 'qrcodes/gps_redirect.html', {
                    'resolve_url': resolve_url,
                    'fallback_url': fallback,
                    'mandatory': False,
                })
            # else: only state/country entries → fall through to GeoIP-based routing below

        # ── GPS-Radius Geo-Fence (Feature 17) ──
        # If this QR has active geo-fence zones, serve the GPS permission page.
        # The ResolveLocationView will check zone containment using Haversine.
        if has_active_geofence(qr):
            # Compute fallback via normal routing (used if GPS is denied)
            gf_fallback = get_video_destination(qr)
            if not gf_fallback:
                gf_fallback = get_pdf_destination(qr)
            if not gf_fallback:
                gf_fallback = get_language_destination(qr, accept_lang_header, country, region, city)
            if not gf_fallback:
                gf_fallback = get_rotation_destination(qr)
            if not gf_fallback:
                gf_fallback = get_time_destination(qr)
            if not gf_fallback:
                gf_fallback = get_device_destination(qr, user_agent)
            if not gf_fallback:
                gf_fallback = qr.destination_url or qr.fallback_url or ''

            resolve_url = request.build_absolute_uri(f'/r/{slug}/resolve-location/')
            logger.info(f"[GeoFence] slug={slug} serving GPS page, fallback={gf_fallback[:80] if gf_fallback else '(none)'}")
            return render(request, 'qrcodes/gps_redirect.html', {
                'resolve_url': resolve_url,
                'fallback_url': gf_fallback,
                'mandatory': False,
            })

        # ── A/B Split Test (Feature 18) ──
        # Cookie stickiness: if visitor was previously assigned a variant, stick with it.
        # Otherwise pick randomly based on weights, then set a cookie.
        if has_active_ab_test(qr):
            cookie_name = f'qr_ab_{qr.id}'
            sticky_idx = None
            raw_cookie = request.COOKIES.get(cookie_name)
            if raw_cookie is not None:
                try:
                    sticky_idx = int(raw_cookie)
                except (ValueError, TypeError):
                    pass

            ab_url, chosen_idx = get_ab_test_destination(qr, sticky_idx)
            if ab_url:
                if ab_url and not ab_url.startswith(('http://', 'https://')):
                    ab_url = 'https://' + ab_url

                # Record analytics in background
                analytics_data = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': ab_url,
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(analytics_data,),
                    daemon=True,
                ).start()

                response = HttpResponseRedirect(ab_url)
                # Set sticky cookie — 30 day expiry
                if chosen_idx is not None:
                    response.set_cookie(
                        cookie_name, str(chosen_idx),
                        max_age=30 * 24 * 60 * 60,  # 30 days
                        httponly=True,
                        samesite='Lax',
                    )
                logger.info(f"[ABTest] slug={slug} variant={chosen_idx} → {ab_url[:80]}")
                return response

        # ── App Deep Link (Feature 19) ──
        # If this QR has an active deep link config, serve an intermediate page
        # that attempts to open the native app, with a web fallback.
        if has_active_deep_link(qr):
            dl_config = get_deep_link_config(qr, user_agent)
            if dl_config:
                dl_link = dl_config.get('deep_link', '')
                dl_fallback = dl_config.get('fallback_url', '')
                dl_platform = dl_config.get('platform', 'other')

                if dl_link or dl_fallback:
                    # Record analytics in background
                    analytics_data = {
                        'qr_id': str(qr.id),
                        'ip': client_ip,
                        'user_agent': user_agent,
                        'referrer': request.META.get('HTTP_REFERER', ''),
                        'language': accept_lang_header[:10] if accept_lang_header else 'en',
                        'country': country,
                        'city': city,
                        'lat': request.GET.get('lat'),
                        'lon': request.GET.get('lon'),
                        'destination_url': dl_link or dl_fallback,
                    }
                    threading.Thread(
                        target=self._record_scan_background,
                        args=(analytics_data,),
                        daemon=True,
                    ).start()

                    # If there's no deep link (desktop), just redirect to fallback
                    if not dl_link and dl_fallback:
                        return HttpResponseRedirect(_append_utm_params(dl_fallback, qr))

                    logger.info(f"[DeepLink] slug={slug} platform={dl_platform} → {dl_link[:80]}")
                    return render(request, 'qrcodes/deep_link_redirect.html', {
                        'deep_link': dl_link,
                        'fallback_url': dl_fallback,
                        'platform': dl_platform,
                    })

        # ── Loyalty Point QR (Feature 26) ──
        # If this QR has an active loyalty program, serve an intermediate page
        # that asks for the scanner's email/phone, then awards points via API.
        try:
            loyalty_prog = qr.loyalty_program
            if loyalty_prog.is_active:
                import json as _json
                dest_url = qr.destination_url or qr.fallback_url or ''
                scan_api = f'/api/v1/qr/{qr.id}/loyalty/scan/'
                tiers_json = _json.dumps(loyalty_prog.reward_tiers or [])
                logger.info(f"[Loyalty] slug={slug} serving loyalty scan page, program={loyalty_prog.program_name}")

                # Record analytics in background (before showing loyalty page)
                _loyalty_analytics = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': dest_url,
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(_loyalty_analytics,),
                    daemon=True,
                ).start()

                return render(request, 'qrcodes/loyalty_scan.html', {
                    'program_name': loyalty_prog.program_name or 'Loyalty Rewards',
                    'points_per_scan': loyalty_prog.points_per_scan,
                    'bonus_points': loyalty_prog.bonus_points,
                    'scan_url': scan_api,
                    'reward_tiers_json': tiers_json,
                    'destination_url': dest_url,
                })
        except Exception:
            pass  # No loyalty program — continue normally

        # ── Digital vCard (Feature 28) ──
        # If this QR has an active vCard, serve the digital business card page.
        try:
            vc = qr.vcard
            if vc.is_active:
                logger.info(f"[vCard] slug={slug} serving digital business card for {vc.full_name()}")
                # Record analytics in background
                _vc_analytics = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': f'vcard:{vc.full_name()}',
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(_vc_analytics,),
                    daemon=True,
                ).start()

                addr_parts = [p for p in [vc.street, vc.city, vc.state, vc.zip_code, vc.country] if p]
                initials = ''
                if vc.first_name:
                    initials += vc.first_name[0].upper()
                if vc.last_name:
                    initials += vc.last_name[0].upper()
                return render(request, 'qrcodes/vcard_page.html', {
                    'vcard': vc,
                    'initials': initials or '?',
                    'address': ', '.join(addr_parts),
                    'download_url': f'/api/v1/qr/{qr.id}/vcard/download/',
                })
        except Exception:
            pass  # No vCard configured — continue normally

        # ── Product Authentication (Feature 31) ──
        # If this QR has active product auth, show the verification page.
        try:
            pa = qr.product_auth
            if pa.is_active:
                logger.info(f"[ProductAuth] slug={slug} serving product verification for {pa.product_name}")
                _pa_analytics = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': f'product-auth:{pa.product_name}',
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(_pa_analytics,),
                    daemon=True,
                ).start()

                prefill_serial = request.GET.get('serial', '')
                return render(request, 'qrcodes/product_verify.html', {
                    'product_name': pa.product_name or 'Product',
                    'manufacturer': pa.manufacturer,
                    'product_image_url': pa.product_image_url,
                    'brand_color': pa.brand_color or '#22c55e',
                    'verify_url': f'/api/v1/qr/{qr.id}/product-auth/verify/',
                    'support_url': pa.support_url,
                    'support_email': pa.support_email,
                    'prefill_serial': prefill_serial,
                })
        except Exception:
            pass  # No product auth — continue normally

        # ── Document Upload Form (Feature 33) ──
        # If this QR has an active doc-upload form, show the upload page.
        try:
            duf = qr.doc_upload_form
            if duf.is_active:
                logger.info(f"[DocUpload] slug={slug} serving doc upload form: {duf.title}")
                _duf_analytics = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': f'doc-upload:{duf.title}',
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(_duf_analytics,),
                    daemon=True,
                ).start()

                return render(request, 'qrcodes/doc_upload.html', {
                    'title': duf.title or 'Upload Documents',
                    'description': duf.description,
                    'allowed_types': duf.allowed_types or [],
                    'allowed_extensions': duf.allowed_extensions,
                    'max_file_size_mb': duf.max_file_size_mb,
                    'max_files': duf.max_files,
                    'require_name': duf.require_name,
                    'require_email': duf.require_email,
                    'require_phone': duf.require_phone,
                    'success_message': duf.success_message,
                    'brand_color': duf.brand_color or '#6366f1',
                    'upload_url': f'/api/v1/qr/{qr.id}/doc-upload/public/',
                })
        except Exception:
            pass  # No doc upload form — continue normally

        # ── Funnel Pages (Feature 34) ──
        try:
            fc = qr.funnel_config
            if fc.is_active and fc.steps.exists():
                logger.info(f"[Funnel] slug={slug} serving funnel: {fc.title}")
                _fc_analytics = {
                    'qr_id': str(qr.id),
                    'ip': client_ip,
                    'user_agent': user_agent,
                    'referrer': request.META.get('HTTP_REFERER', ''),
                    'language': accept_lang_header[:10] if accept_lang_header else 'en',
                    'country': country,
                    'city': city,
                    'lat': request.GET.get('lat'),
                    'lon': request.GET.get('lon'),
                    'destination_url': f'funnel:{fc.title}',
                }
                threading.Thread(
                    target=self._record_scan_background,
                    args=(_fc_analytics,),
                    daemon=True,
                ).start()

                import json as _json
                steps_qs = fc.steps.all()
                steps_list = [
                    {
                        'title': s.title,
                        'content': s.content,
                        'image_url': s.image_url,
                        'button_text': s.button_text,
                        'button_url': s.button_url,
                    }
                    for s in steps_qs
                ]
                return render(request, 'qrcodes/funnel_page.html', {
                    'title': fc.title or 'Welcome',
                    'brand_color': fc.brand_color or '#6366f1',
                    'show_progress_bar': fc.show_progress_bar,
                    'allow_back': fc.allow_back_navigation,
                    'steps_json': _json.dumps(steps_list),
                    'track_url': f'/api/v1/qr/{qr.id}/funnel/track/',
                })
        except Exception:
            pass  # No funnel config — continue normally

        # 5a. Video player (highest priority — inline video playback)
        destination = get_video_destination(qr)
        if destination:
            logger.info(f"[Scan] slug={slug} matched: video_player → {destination[:80]}")

        # 5b. PDF viewer (inline PDF without download)
        if not destination:
            destination = get_pdf_destination(qr)
            if destination:
                logger.info(f"[Scan] slug={slug} matched: pdf_viewer → {destination[:80]}")

        # 5b. Language-based routing (geo-targeted)
        if not destination:
            destination = get_language_destination(qr, accept_lang_header, country, region, city)
            if destination:
                logger.info(f"[Scan] slug={slug} matched: language_route → {destination[:80]}")

        # 5c. Auto-rotation schedule (overrides routing rules but not language)
        if not destination:
            destination = get_rotation_destination(qr)
            if destination:
                logger.info(f"[Scan] slug={slug} matched: rotation → {destination[:80]}")

        # 5d. Time-based schedule (e.g. breakfast/lunch/dinner)
        if not destination:
            destination = get_time_destination(qr)
            if destination:
                logger.info(f"[Scan] slug={slug} matched: time_schedule → {destination[:80]}")

        # 5e. Device-based redirect (Android / iOS / Windows / Mac / Tablet)
        if not destination:
            destination = get_device_destination(qr, user_agent)
            if destination:
                logger.info(f"[Scan] slug={slug} matched: device_route → {destination[:80]}")

        # 5f. Evaluate routing rules if no higher-priority match
        if not destination:
            ua_lower = user_agent.lower()
            minimal_context = {
                'device_type': 'mobile' if any(m in ua_lower for m in ['mobile', 'android', 'iphone', 'ipad']) else 'desktop',
                'country': country,
                'language': accept_lang_header[:10] if accept_lang_header else 'en',
            }
            destination = evaluate_rules(qr, minimal_context)

        if not destination:
            return JsonResponse({'error': 'No destination configured.'}, status=404)

        # 6. Capture analytics data NOW (cheap — just reading request headers)
        #    but process it in a background thread so redirect fires instantly
        analytics_data = {
            'qr_id': str(qr.id),
            'org_id': str(qr.organization_id) if qr.organization_id else '',
            'slug': qr.slug,
            'ip': client_ip,
            'user_agent': user_agent,
            'referrer': request.META.get('HTTP_REFERER', ''),
            'language': accept_lang_header[:10] if accept_lang_header else 'en',
            'country': country,
            'city': city,  # Already resolved — avoid duplicate GeoIP in background
            'lat': request.GET.get('lat'),
            'lon': request.GET.get('lon'),
            'destination_url': destination,
            'scan_count': qr.total_scans,
        }
        threading.Thread(
            target=self._record_scan_background,
            args=(analytics_data,),
            daemon=True,
        ).start()

        # 7. REDIRECT — fires immediately, analytics happens behind the scenes
        # Ensure the destination is an absolute URL so browsers don't treat it
        # as a relative path and resolve it against the current /r/<slug>/ URL.
        if destination and not destination.startswith(('http://', 'https://')):
            destination = 'https://' + destination

        # Self-heal: rewrite any legacy localhost URLs to the production domain.
        if destination and 'localhost' in destination:
            from django.conf import settings as _s
            prod_base = getattr(_s, 'SITE_BASE_URL', '').rstrip('/')
            if prod_base and 'localhost' not in prod_base:
                destination = destination.replace('http://localhost:8000', prod_base)
                destination = destination.replace('http://localhost', prod_base)

        logger.info(f"Redirect: {slug} -> {destination[:80]}")
        response = HttpResponseRedirect(_append_utm_params(destination, qr))
        # Prevent browser caching of 302 so every scan hits the server for analytics
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        return response

    # ── Background workers (run in daemon threads, no impact on response time) ──

    @staticmethod
    def _record_scan_background(data: dict):
        """
        Runs in a daemon thread after redirect response is already sent.
        Does all the heavy work: GeoIP, counter increment, DB write, Celery task.
        """
        import django
        # Ensure Django is set up (needed when running outside request cycle)
        try:
            from django.db import connection
            from django.db.models import F
            from apps.qrcodes.models import QRCode

            qr_id = data['qr_id']
            ip = data['ip']
            user_agent = data.get('user_agent', '')
            ua_lower = user_agent.lower()

            # Parse device/browser/OS (cheap string ops, fine in background)
            device_type = 'mobile' if any(m in ua_lower for m in ['mobile', 'android', 'iphone', 'ipad']) else 'desktop'
            os_name = 'unknown'
            if 'android' in ua_lower: os_name = 'android'
            elif 'iphone' in ua_lower or 'ipad' in ua_lower: os_name = 'ios'
            elif 'windows' in ua_lower: os_name = 'windows'
            elif 'mac' in ua_lower: os_name = 'mac'
            elif 'linux' in ua_lower: os_name = 'linux'

            browser = 'unknown'
            if 'chrome' in ua_lower and 'edg' not in ua_lower: browser = 'chrome'
            elif 'safari' in ua_lower and 'chrome' not in ua_lower: browser = 'safari'
            elif 'firefox' in ua_lower: browser = 'firefox'
            elif 'edg' in ua_lower: browser = 'edge'

            # GeoIP — resolve country, city, AND lat/lng for the scan-map
            country = data.get('country', '')
            city = ''
            scan_lat = float(data['lat']) if data.get('lat') else None
            scan_lng = float(data['lon']) if data.get('lon') else None

            # 1. Try local geoip2 DB first (fastest, no network)
            try:
                from django.conf import settings
                import os as _os
                geoip_path = getattr(settings, 'GEOIP_DB_PATH', '')
                if geoip_path and _os.path.isfile(geoip_path):
                    import geoip2.database
                    with geoip2.database.Reader(geoip_path) as reader:
                        geo = reader.city(ip)
                        if not country:
                            country = geo.country.iso_code or ''
                        city = geo.city.name or ''
            except Exception:
                pass  # GeoIP DB unavailable — continue to API fallback

            # 2. If still no lat/lng and IP is public, call ip-api.com to get coords
            _PRIV = ('127.', '10.', '192.168.', '172.16.', '172.17.',
                     '172.18.', '172.19.', '172.20.', '172.21.', '172.22.',
                     '172.23.', '172.24.', '172.25.', '172.26.', '172.27.',
                     '172.28.', '172.29.', '172.30.', '172.31.', '::1')
            _is_private = ip and any(ip.startswith(p) for p in _PRIV)

            if not scan_lat and not _is_private and ip:
                try:
                    import json as _json
                    from urllib.request import urlopen as _urlopen, Request as _Req
                    # ipinfo.io — HTTPS, free, whitelisted on PythonAnywhere
                    _url = f"https://ipinfo.io/{ip}/json"
                    _req = _Req(_url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
                    with _urlopen(_req, timeout=3) as _resp:
                        _d = _json.loads(_resp.read().decode())
                    _loc = _d.get('loc', '')  # "lat,lng"
                    if _loc and ',' in _loc:
                        _parts = _loc.split(',')
                        scan_lat = float(_parts[0])
                        scan_lng = float(_parts[1])
                    if not city:
                        city = _d.get('city', '')
                    if not country:
                        country = _d.get('country', '')
                except Exception:
                    pass  # Network failure — lat/lng stays None

            # 3. ipapi.co fallback if ipinfo.io failed
            if not scan_lat and not _is_private and ip:
                try:
                    import json as _json
                    from urllib.request import urlopen as _urlopen, Request as _Req
                    _url = f"https://ipapi.co/{ip}/json/"
                    _req = _Req(_url, headers={'User-Agent': 'QRGenie/1.0'})
                    with _urlopen(_req, timeout=4) as _resp:
                        _d = _json.loads(_resp.read().decode())
                    scan_lat = _d.get('latitude') or _d.get('lat')
                    scan_lng = _d.get('longitude') or _d.get('lon')
                    if not city:
                        city = _d.get('city', '')
                    if not country:
                        country = _d.get('country_code', '')
                except Exception:
                    pass

            # Increment counter (single UPDATE, very fast)
            QRCode.objects.filter(id=qr_id).update(total_scans=F('total_scans') + 1)

            # Feature 21: Increment expiry scan counter if scan_count mode
            try:
                from apps.qrcodes.models import QRExpiry
                exp = QRExpiry.objects.filter(qr_code_id=qr_id, is_active=True, expiry_type='scan_count').first()
                if exp:
                    QRExpiry.objects.filter(pk=exp.pk).update(scan_count=F('scan_count') + 1)
            except Exception:
                pass

            # ── Write ScanEvent directly to DB ──
            # (Celery is not reliable on PythonAnywhere free tier — no worker running)
            try:
                from apps.analytics.models import ScanEvent
                import hashlib
                today = timezone.now().date().isoformat()
                raw_fp = f"{ip}:{user_agent}:{qr_id}:{today}"
                fingerprint = hashlib.sha256(raw_fp.encode()).hexdigest()
                is_unique = not ScanEvent.objects.filter(
                    qr_code_id=qr_id, fingerprint=fingerprint,
                ).exists()
                ScanEvent.objects.create(
                    qr_code_id=qr_id,
                    ip_address=ip,
                    country=country,
                    city=city,
                    device_type=device_type,
                    os=os_name,
                    browser=browser,
                    language=data.get('language', ''),
                    user_agent=user_agent[:512],
                    referrer=data.get('referrer', '')[:1024],
                    latitude=float(scan_lat) if scan_lat else None,
                    longitude=float(scan_lng) if scan_lng else None,
                    destination_url=data.get('destination_url', '')[:2048],
                    fingerprint=fingerprint,
                    is_unique=is_unique,
                )
                QRCode.objects.filter(id=qr_id).update(
                    unique_scans=F('unique_scans') + (1 if is_unique else 0)
                )
                logger.info(f"[Scan] ScanEvent saved: qr={qr_id} ip={ip[:8]}*** lat={scan_lat} lng={scan_lng}")
            except Exception as e:
                logger.error(f"Direct scan record failed: {e}")

            # ── Also try Celery if available (no-op if no worker) ──
            try:
                from apps.analytics.tasks import record_scan_event
                record_scan_event.delay(
                    qr_id=qr_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    device_type=device_type,
                    os=os_name,
                    browser=browser,
                    country=country,
                    city=city,
                    language=data.get('language', ''),
                    referrer=data.get('referrer', ''),
                    latitude=float(scan_lat) if scan_lat else None,
                    longitude=float(scan_lng) if scan_lng else None,
                    destination_url=data.get('destination_url', ''),
                )
            except Exception:
                pass  # Celery unavailable — already saved above

            # ── Feature 25: Scan Alert Notifications ──
            try:
                from apps.qrcodes.services import send_scan_alert_email
                send_scan_alert_email(
                    qr_id=str(qr_id),
                    ip=ip,
                    city=city,
                    country=country,
                )
            except Exception as e:
                logger.error(f"Scan alert check failed: {e}")

            # ── Fire Webhooks (scan.created event) ──
            try:
                from apps.webhooks.tasks import dispatch_webhook_event
                scan_payload = {
                    'event': 'scan.created',
                    'qr_id': str(qr_id),
                    'slug': data.get('slug', ''),
                    'ip_address': ip,
                    'country': country,
                    'city': city,
                    'device_type': device_type,
                    'os': os_name,
                    'browser': browser,
                    'destination_url': data.get('destination_url', ''),
                    'scanned_at': timezone.now().isoformat(),
                }
                org_id = data.get('org_id', '')
                if org_id:
                    dispatch_webhook_event(event_type='scan.created', payload=scan_payload, org_id=org_id)
            except Exception as e:
                logger.error(f"Webhook dispatch failed: {e}")

            # ── Fire Automation triggers ──
            try:
                from apps.automation.tasks import fire_automation_trigger
                auto_context = {
                    'qr_id': str(qr_id),
                    'country': country,
                    'city': city,
                    'device_type': device_type,
                    'os': os_name,
                    'browser': browser,
                    'ip_address': ip,
                    'scan_count': data.get('scan_count', 0),
                }
                org_id = data.get('org_id', '')
                fire_automation_trigger(
                    trigger_type='scan_created',
                    context=auto_context,
                    org_id=org_id,
                    qr_id=str(qr_id),
                )
                # Also fire specialised scan triggers
                if auto_context.get('country'):
                    fire_automation_trigger(
                        trigger_type='scan_from_country',
                        context=auto_context,
                        org_id=org_id,
                        qr_id=str(qr_id),
                    )
                if auto_context.get('device_type'):
                    fire_automation_trigger(
                        trigger_type='scan_device_type',
                        context=auto_context,
                        org_id=org_id,
                        qr_id=str(qr_id),
                    )
                # Check scan_limit_reached
                try:
                    qr_obj = QRCode.objects.only('scan_limit', 'total_scans').get(id=qr_id)
                    if qr_obj.scan_limit and qr_obj.total_scans >= qr_obj.scan_limit:
                        fire_automation_trigger(
                            trigger_type='scan_limit_reached',
                            context=auto_context,
                            org_id=org_id,
                            qr_id=str(qr_id),
                        )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Automation trigger failed: {e}")

            connection.close()  # Always close thread-local DB connection

        except Exception as e:
            logger.error(f"Background scan record error: {e}")

    @staticmethod
    def _expire_qr(qr_id: str):
        """Set QR status to expired in background."""
        try:
            from apps.qrcodes.models import QRCode
            from django.db import connection
            qr = QRCode.objects.filter(id=qr_id).first()
            if qr:
                qr.status = 'expired'
                qr.save(update_fields=['status'])
                # Fire automation trigger: qr_expired
                try:
                    from apps.automation.tasks import fire_automation_trigger
                    fire_automation_trigger(
                        trigger_type='qr_expired',
                        context={
                            'qr_id': str(qr.id),
                            'title': qr.title,
                            'slug': qr.slug,
                            'total_scans': qr.total_scans,
                        },
                        org_id=str(qr.organization_id) if qr.organization_id else '',
                        qr_id=str(qr.id),
                    )
                except Exception:
                    pass
            connection.close()
        except Exception:
            pass


class GeoDebugView(View):
    """
    GET /r/geo-debug/?ip=<ip>   — returns raw GeoIP data for diagnosis.
    GET /r/geo-debug/           — uses the requester's own IP.
    Also clears the cached GeoIP result so a fresh lookup is forced.
    """
    def get(self, request):
        from apps.core.utils import get_client_ip
        ip = request.GET.get('ip') or get_client_ip(request)
        # Clear cached result so we get a fresh lookup
        cache_key = f"geoip:{ip}"
        cache.delete(cache_key)
        country, region, city = _fast_geoip_lookup(ip)
        return JsonResponse({
            'ip': ip,
            'country': country,
            'region': region,
            'city': city,
            'note': (
                'district matching compares city (above) against your configured district name. '
                'If city is empty or wrong, district routing will miss. '
                'Use the exact city value shown above in your District (opt) field.'
            ),
        })


class MyLocationView(View):
    """
    GET /api/v1/qr/my-location/
    Returns the approximate lat/lng + city for the requester's public IP.
    Used by the dashboard Leaflet map — no auth required, reads caller's own IP.
    """
    def get(self, request):
        ip = get_client_ip(request)

        # Localhost / dev → default to center of India
        if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
            return JsonResponse({
                'lat': 20.5937, 'lng': 78.9629,
                'city': '', 'region': '', 'country': 'IN',
                'label': 'India (approximate)',
            })

        cache_key = f"my_location:{ip}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        # ipinfo.io — HTTPS, free 50k/mo, whitelisted on PythonAnywhere
        try:
            url = f"https://ipinfo.io/{ip}/json"
            req = Request(url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
            with urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            loc = data.get('loc', '')  # "lat,lng"
            if loc and ',' in loc:
                parts = loc.split(',')
                lat_f, lng_f = float(parts[0]), float(parts[1])
                city    = data.get('city', '')
                region  = data.get('region', '')
                country_code = data.get('country', '')
                label   = ', '.join(p for p in [city, region, country_code] if p)
                result = {
                    'lat':     lat_f,
                    'lng':     lng_f,
                    'city':    city,
                    'region':  region,
                    'country': country_code,
                    'label':   label or 'Your approximate location',
                }
                cache.set(cache_key, result, timeout=3600)
                return JsonResponse(result)
        except Exception as e:
            logger.warning(f"[MyLocation] ipinfo.io failed for {ip}: {e}")

        # ipapi.co fallback
        try:
            url = f"https://ipapi.co/{ip}/json/"
            req = Request(url, headers={'User-Agent': 'QRGenie/1.0'})
            with urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            lat = data.get('latitude') or data.get('lat')
            lng = data.get('longitude') or data.get('lon')
            if lat and lng:
                city    = data.get('city', '')
                region  = data.get('region', '')
                country = data.get('country_name', '')
                label   = ', '.join(p for p in [city, region, country] if p)
                result = {
                    'lat': float(lat), 'lng': float(lng),
                    'city': city, 'region': region,
                    'country': data.get('country_code', ''),
                    'label': label or 'Your approximate location',
                }
                cache.set(cache_key, result, timeout=3600)
                return JsonResponse(result)
        except Exception as e:
            logger.warning(f"[MyLocation] ipapi.co failed for {ip}: {e}")

        return JsonResponse({
            'lat': 20.5937, 'lng': 78.9629,
            'city': '', 'region': '', 'country': '',
            'label': 'Location unavailable',
        })


def _reverse_geocode_nominatim(lat: float, lng: float) -> tuple[str, str, str]:
    """
    Convert GPS coordinates → (district, state_code, country_code) using
    OpenStreetMap Nominatim (free, no API key required).

    For India the mapping is:
      address.county          → district  (e.g. "Vizianagaram")
      address.state_district  → fallback  (e.g. "Vizianagaram District")
      address.state           → state name (e.g. "Andhra Pradesh")
      address.country_code    → "in"

    Returns ("", "", "") on any failure.
    """
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lng}&format=json&addressdetails=1&zoom=10"
        )
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0'})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        address = data.get('address', {})

        # District — try fields in order of specificity for India
        district = (
            address.get('county', '')
            or address.get('city_district', '')
            or address.get('city', '')
            or address.get('town', '')
            or address.get('village', '')
            or address.get('state_district', '').replace(' District', '').strip()
            or ''
        )
        state_name = address.get('state', '')
        country_code = (address.get('country_code', '') or '').upper()

        # Map India state names → ISO codes
        _IN_STATE_MAP = {
            'andhra pradesh': 'AP', 'telangana': 'TG', 'tamil nadu': 'TN',
            'karnataka': 'KA', 'kerala': 'KL', 'maharashtra': 'MH',
            'west bengal': 'WB', 'gujarat': 'GJ', 'odisha': 'OR',
            'punjab': 'PB', 'assam': 'AS', 'bihar': 'BR',
            'madhya pradesh': 'MP', 'rajasthan': 'RJ', 'uttar pradesh': 'UP',
            'uttarakhand': 'UT', 'jharkhand': 'JH', 'chhattisgarh': 'CT',
            'himachal pradesh': 'HP', 'haryana': 'HR', 'goa': 'GA',
            'manipur': 'MN', 'meghalaya': 'ML', 'mizoram': 'MZ',
            'nagaland': 'NL', 'arunachal pradesh': 'AR', 'sikkim': 'SK',
            'tripura': 'TR', 'delhi': 'DL',
        }
        state_code = _IN_STATE_MAP.get(state_name.lower().strip(), state_name)

        logger.info(
            f"[GPS] Nominatim reverse geocode ({lat},{lng}) → "
            f"district={district}, state={state_code}, country={country_code}"
        )
        return (district, state_code, country_code)
    except Exception as e:
        logger.warning(f"[GPS] Nominatim reverse geocode failed for ({lat},{lng}): {e}")
        return ('', '', '')


def _match_geo_direct_by_district(lang_route, district: str) -> str | None:
    """
    Match geo_direct entries by district name (fuzzy, supports comma-separated aliases).
    Returns URL string or None.
    """
    if not district:
        return None
    geo_direct = getattr(lang_route, 'geo_direct', None) or []
    district_lower = district.lower().strip()
    for entry in geo_direct:
        e_district_raw = (entry.get('district', '') or '').lower().strip()
        if not e_district_raw:
            continue
        aliases = [a.strip() for a in e_district_raw.split(',') if a.strip()]
        if any(
            alias == district_lower or alias in district_lower or district_lower in alias
            for alias in aliases
        ):
            url = entry.get('url', '')
            if url:
                logger.info(f"[GPS] geo_direct district match: '{district}' matched aliases={aliases} → {url[:80]}")
                return url
    return None


@method_decorator(csrf_exempt, name='dispatch')
class ResolveLocationView(View):
    """
    POST /r/<slug>/resolve-location/
    Body: {"lat": 17.6868, "lng": 83.2185}

    Called by the GPS redirect page after the browser returns coordinates.
    Reverse geocodes with Nominatim, matches geo_direct entries,
    then falls back to normal language routing, then QR destination.
    Returns {"url": "https://..."}.
    """
    def post(self, request, slug):
        try:
            body = json.loads(request.body)
            lat = float(body.get('lat', 0))
            lng = float(body.get('lng', 0))
        except (ValueError, TypeError, KeyError):
            return JsonResponse({'error': 'invalid body'}, status=400)

        if lat == 0 and lng == 0:
            return JsonResponse({'error': 'invalid coordinates'}, status=400)

        qr = get_qr_from_cache(slug)
        if not qr:
            return JsonResponse({'error': 'not found'}, status=404)

        # Reverse geocode GPS → district
        district, state_code, country_code = _reverse_geocode_nominatim(lat, lng)

        # Try geo_direct district match first
        url = None
        try:
            lang_route = qr.language_route
            if lang_route and lang_route.is_active:
                # ── Mandatory GPS: cache device IP → coords ──
                if getattr(lang_route, 'mandatory_location', False):
                    from .models import DeviceLocationCache
                    client_ip = get_client_ip(request)
                    DeviceLocationCache.objects.update_or_create(
                        ip_address=client_ip,
                        defaults={'latitude': lat, 'longitude': lng},
                    )
                    logger.info(f"[GPS] Cached location for IP {client_ip}: ({lat:.4f}, {lng:.4f})")

                url = _match_geo_direct_by_district(lang_route, district)
                if not url and state_code and country_code:
                    # Full language destination with real GPS-derived city
                    accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
                    url = get_language_destination(
                        qr, accept_lang, country_code, state_code, district
                    )
        except ObjectDoesNotExist:
            # QR has no language_route — not an error, continue to geofence check
            logger.debug(f"[GPS] ResolveLocation slug={slug}: no language_route, skipping lang/geo_direct")
        except Exception as e:
            logger.warning(f"[GPS] ResolveLocation lang_route error for {slug}: {e}")

        # ── GPS-Radius Geo-Fence (Feature 17) ──
        # Check if user's GPS coords are inside any geo-fence zone.
        if not url:
            url = get_geofence_destination(qr, lat, lng)

        # Final fallback: QR's own destination
        if not url:
            url = qr.destination_url or qr.fallback_url or ''

        logger.info(f"[GPS] ResolveLocation slug={slug} district={district} → {url[:80]}")

        # ── Backfill GPS coords onto the scan event recorded during the initial GET ──
        # The initial redirect recorded a ScanEvent with no lat/lng (GPS wasn't collected yet).
        # Now we have real GPS coords — patch the most recent event for this IP + QR.
        try:
            from apps.analytics.models import ScanEvent
            client_ip = get_client_ip(request)
            recent = (
                ScanEvent.objects
                .filter(qr_code=qr, ip_address=client_ip, latitude__isnull=True)
                .order_by('-scanned_at')
                .first()
            )
            if recent:
                recent.latitude = lat
                recent.longitude = lng
                recent.save(update_fields=['latitude', 'longitude'])
                logger.info(f"[GPS] Backfilled lat/lng onto ScanEvent {recent.id} for IP {client_ip}")
        except Exception as e:
            logger.warning(f"[GPS] Failed to backfill scan lat/lng: {e}")

        return JsonResponse({'url': url})
