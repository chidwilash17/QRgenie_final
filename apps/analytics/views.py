"""
Analytics Views
================
Provides per-QR analytics endpoints: summary, scan events, daily metrics,
scan map (lat/lng heatmap), debug tools, and backfill utilities.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models.functions import TruncDate, ExtractHour
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import ScanEvent, DailyMetric, LinkClickEvent, ConversionEvent
from .serializers import (
    ScanEventSerializer,
    DailyMetricSerializer,
    ConversionEventSerializer,
)

logger = logging.getLogger('apps.analytics')


def _resolve_ip_to_latlng(ip: str):
    """
    Resolve a public IP address -> (lat, lng, city, country).
    Uses ipinfo.io (HTTPS) -> ipapi.co fallback.
    Caches result 1 hour. Returns (None, None, '', '') on failure.
    """
    if not ip:
        return None, None, '', ''

    _PRIV = (
        '127.', '10.', '192.168.',
        '172.16.', '172.17.', '172.18.', '172.19.', '172.20.',
        '172.21.', '172.22.', '172.23.', '172.24.', '172.25.',
        '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.',
        '::1',
    )
    if any(ip.startswith(p) for p in _PRIV):
        return None, None, '', ''

    from django.core.cache import cache
    cache_key = f"latlng:{ip}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    import json
    from urllib.request import urlopen, Request
    from urllib.error import URLError

    try:
        url = f"https://ipinfo.io/{ip}/json"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        loc = data.get('loc', '')
        if loc and ',' in loc:
            parts = loc.split(',')
            lat = float(parts[0])
            lng = float(parts[1])
            city = data.get('city', '')
            country = data.get('country', '')
            result = (lat, lng, city, country)
            cache.set(cache_key, result, timeout=3600)
            logger.info(f"[GeoIP] ipinfo.io {ip} -> {lat},{lng} {city} {country}")
            return result
        else:
            logger.warning(f"[GeoIP] ipinfo.io no loc for {ip}: {data}")
    except (URLError, Exception) as e:
        logger.warning(f"[GeoIP] ipinfo.io failed for {ip}: {e}")

    try:
        url = f"https://ipapi.co/{ip}/json/"
        req = Request(url, headers={'User-Agent': 'QRGenie/1.0'})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        lat = data.get('latitude') or data.get('lat')
        lng = data.get('longitude') or data.get('lon')
        if lat and lng:
            city = data.get('city', '')
            country = data.get('country_code', '')
            result = (float(lat), float(lng), city, country)
            cache.set(cache_key, result, timeout=3600)
            logger.info(f"[GeoIP] ipapi.co {ip} -> {lat},{lng} {city} {country}")
            return result
        else:
            logger.warning(f"[GeoIP] ipapi.co no coords for {ip}: {data}")
    except Exception as e:
        logger.warning(f"[GeoIP] ipapi.co failed for {ip}: {e}")

    return None, None, '', ''


class ScanMapView(APIView):
    """
    GET /api/v1/analytics/qr/<qr_id>/scan-map/?period=30

    Returns map markers for all scan locations.
    Each unique public IP shown once (GPS > stored GeoIP > live GeoIP).
    Response: [{ lat, lng, count, city, country, source }, ...]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, qr_id):
        period_days = int(request.query_params.get('period', 30))
        cutoff = timezone.now() - timedelta(days=period_days)

        qs = ScanEvent.objects.filter(
            qr_code_id=qr_id,
            scanned_at__gte=cutoff,
        ).values(
            'id', 'ip_address', 'latitude', 'longitude',
            'city', 'country', 'scanned_at',
        ).order_by('scanned_at')

        raw_scans = list(qs)
        all_ips = list({r['ip_address'] for r in raw_scans if r['ip_address']})
        logger.warning(
            f"[ScanMap] qr={qr_id} period={period_days}d "
            f"raw_scans={len(raw_scans)} ips={all_ips[:10]}"
        )

        total_ever = ScanEvent.objects.filter(qr_code_id=qr_id).count()
        logger.warning(
            f"[ScanMap] qr={qr_id} total_ever_in_db={total_ever} "
            f"oldest_cutoff={cutoff.date()}"
        )

        if not raw_scans:
            logger.warning(f"[ScanMap] qr={qr_id} returning 0 markers")
            return Response([])

        ip_groups: dict = {}
        for row in raw_scans:
            ip = row['ip_address'] or 'unknown'
            entry = ip_groups.setdefault(ip, {
                'count': 0, 'lat': None, 'lng': None,
                'city': '', 'country': '', 'source': '',
                'ids_without_coords': [],
            })
            entry['count'] += 1
            if row['latitude'] and row['longitude']:
                entry['lat'] = row['latitude']
                entry['lng'] = row['longitude']
                entry['city'] = row['city'] or entry['city']
                entry['country'] = row['country'] or entry['country']
                entry['source'] = 'gps'
            elif not entry['lat']:
                entry['ids_without_coords'].append(row['id'])
                if row['city']:
                    entry['city'] = row['city']
                if row['country']:
                    entry['country'] = row['country']

        markers = []
        needs_save = []

        for ip, grp in ip_groups.items():
            lat, lng = grp['lat'], grp['lng']
            source = grp['source']

            if not lat and ip != 'unknown':
                lat, lng, city, country = _resolve_ip_to_latlng(ip)
                if lat:
                    if not grp['city']:
                        grp['city'] = city
                    if not grp['country']:
                        grp['country'] = country
                    source = 'geoip'
                    if grp['ids_without_coords']:
                        needs_save.append((grp['ids_without_coords'], lat, lng))

            if lat and lng:
                markers.append({
                    'lat': lat,
                    'lng': lng,
                    'count': grp['count'],
                    'city': grp['city'],
                    'country': grp['country'],
                    'source': source or 'geoip',
                })

        if needs_save:
            def _save():
                try:
                    for ids, lat, lng in needs_save:
                        ScanEvent.objects.filter(id__in=ids).update(
                            latitude=lat, longitude=lng
                        )
                    logger.info(f"[ScanMap] Self-healed {sum(len(x[0]) for x in needs_save)} events")
                except Exception as exc:
                    logger.warning(f"[ScanMap] Self-heal save failed: {exc}")
            import threading
            threading.Thread(target=_save, daemon=True).start()

        logger.warning(f"[ScanMap] qr={qr_id} returning {len(markers)} markers")
        return Response(markers)


class ScanMapDebugView(APIView):
    """
    GET /api/v1/analytics/qr/<qr_id>/scan-map/debug/
    Returns raw stored scan events + live ipinfo.io connectivity test.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, qr_id):
        import json
        from urllib.request import urlopen, Request
        from urllib.error import URLError
        from apps.core.utils import get_client_ip

        events = list(
            ScanEvent.objects.filter(qr_code_id=qr_id)
            .order_by('-scanned_at')
            .values('id', 'ip_address', 'latitude', 'longitude', 'city', 'country', 'scanned_at', 'fingerprint')[:20]
        )
        for e in events:
            e['id'] = str(e['id'])
            e['scanned_at'] = e['scanned_at'].isoformat() if e['scanned_at'] else None

        total = ScanEvent.objects.filter(qr_code_id=qr_id).count()

        test_ip = get_client_ip(request)
        ipinfo_result = {'_status': 'NOT_RUN', '_ip': test_ip}
        try:
            url = f"https://ipinfo.io/{test_ip}/json"
            req = Request(url, headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'})
            with urlopen(req, timeout=5) as resp:
                ipinfo_result = json.loads(resp.read().decode())
                ipinfo_result['_status'] = 'SUCCESS'
                ipinfo_result['_ip'] = test_ip
        except (URLError, Exception) as e:
            ipinfo_result['_status'] = 'FAILED'
            ipinfo_result['_error'] = str(e)

        return Response({
            'qr_id': str(qr_id),
            'total_events': total,
            'recent_events': events,
            'ipinfo_connectivity': ipinfo_result,
        })


class BackfillLocationsView(APIView):
    """
    POST /api/v1/analytics/backfill-locations/
    Resolve lat/lng for all ScanEvents that have an IP but no coordinates.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        null_events = (
            ScanEvent.objects.filter(latitude__isnull=True, ip_address__isnull=False)
            .exclude(ip_address='')
            .values('ip_address')
            .distinct()
        )

        resolved = 0
        failed = 0
        failed_ips = []

        for entry in null_events:
            ip = entry['ip_address']
            lat, lng, city, country = _resolve_ip_to_latlng(ip)
            if lat:
                updated = ScanEvent.objects.filter(
                    ip_address=ip, latitude__isnull=True
                ).update(latitude=lat, longitude=lng)
                resolved += updated
            else:
                failed += 1
                failed_ips.append(ip)

        return Response({
            'resolved': resolved,
            'failed': failed,
            'failed_ips': failed_ips[:20],
            'message': f'Backfilled coordinates for {resolved} events.',
        })


class AnalyticsSummaryView(APIView):
    """
    GET /api/v1/analytics/summary/
    Returns org-wide scan stats for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.qrcodes.models import QRCode
        from django.db.models import Count as DjCount
        from datetime import date

        org = request.user.organization
        user_qr_ids = QRCode.objects.filter(organization=org).values_list('id', flat=True)

        today = date.today()
        week_start = today - timedelta(days=7)
        month_start = today - timedelta(days=30)

        base_qs = ScanEvent.objects.filter(qr_code_id__in=user_qr_ids)

        total_scans = base_qs.count()
        unique_scans = base_qs.filter(is_unique=True).count()
        scans_today = base_qs.filter(scanned_at__date=today).count()
        scans_this_week = base_qs.filter(scanned_at__date__gte=week_start).count()
        scans_this_month = base_qs.filter(scanned_at__date__gte=month_start).count()

        top_countries = list(
            base_qs.exclude(country='').values('country')
            .annotate(count=DjCount('id')).order_by('-count')[:5]
        )
        top_devices = list(
            base_qs.exclude(device_type='').values('device_type')
            .annotate(count=DjCount('id')).order_by('-count')[:5]
        )
        top_qr_codes = list(
            QRCode.objects.filter(id__in=user_qr_ids)
            .order_by('-total_scans').values('id', 'slug', 'title', 'total_scans')[:5]
        )
        for q in top_qr_codes:
            q['id'] = str(q['id'])
            q['scans'] = q.pop('total_scans', 0)

        daily_trend_raw = list(
            base_qs.filter(scanned_at__date__gte=month_start)
            .annotate(day=TruncDate('scanned_at'))
            .values('day').annotate(count=DjCount('id')).order_by('day')
        )
        # Build a lookup and fill every day in the range with 0 if missing
        scan_by_day = {str(row['day']): row['count'] for row in daily_trend_raw}
        daily_trend = []
        for i in range(30):
            d = month_start + timedelta(days=i)
            daily_trend.append({'date': str(d), 'scans': scan_by_day.get(str(d), 0)})

        return Response({
            'total_scans': total_scans,
            'unique_scans': unique_scans,
            'total_qr_codes': QRCode.objects.filter(organization=org).count(),
            'scans_today': scans_today,
            'scans_this_week': scans_this_week,
            'scans_this_month': scans_this_month,
            'top_countries': top_countries,
            'top_devices': top_devices,
            'top_qr_codes': top_qr_codes,
            'daily_trend': daily_trend,
        })


class QRAnalyticsView(APIView):
    """
    GET /api/v1/analytics/qr/<qr_id>/?period=30
    Per-QR analytics breakdown.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, qr_id):
        from apps.qrcodes.models import QRCode
        from django.db.models import Count as DjCount

        try:
            qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
        except QRCode.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        period_days = int(request.query_params.get('period', 30))
        cutoff = timezone.now() - timedelta(days=period_days)
        qs = ScanEvent.objects.filter(qr_code=qr, scanned_at__gte=cutoff)

        total = qs.count()
        unique = qs.filter(is_unique=True).count()

        country_breakdown = list(
            qs.exclude(country='').values('country')
            .annotate(count=DjCount('id')).order_by('-count')[:10]
        )
        device_breakdown = list(
            qs.exclude(device_type='').values('device_type')
            .annotate(count=DjCount('id')).order_by('-count')
        )
        browser_breakdown = list(
            qs.exclude(browser='').values('browser')
            .annotate(count=DjCount('id')).order_by('-count')[:8]
        )
        os_breakdown = list(
            qs.exclude(os='').values('os')
            .annotate(count=DjCount('id')).order_by('-count')[:8]
        )
        hourly_breakdown = list(
            qs.annotate(hour=ExtractHour('scanned_at'))
            .values('hour').annotate(count=DjCount('id')).order_by('hour')
        )
        daily_trend_raw = list(
            qs.annotate(day=TruncDate('scanned_at'))
            .values('day').annotate(count=DjCount('id')).order_by('day')
        )
        # Fill every day in the period with 0 if no scans
        scan_by_day = {str(row['day']): row['count'] for row in daily_trend_raw}
        daily_trend = []
        today = timezone.now().date()
        for i in range(period_days):
            d = (today - timedelta(days=period_days - 1 - i))
            daily_trend.append({'date': str(d), 'scans': scan_by_day.get(str(d), 0)})

        # Referrer breakdown
        referrer_breakdown = list(
            qs.exclude(referrer='').values('referrer')
            .annotate(count=DjCount('id')).order_by('-count')[:10]
        )

        # Conversion events for this QR
        conv_qs = ConversionEvent.objects.filter(qr_code=qr, created_at__gte=cutoff)
        total_conversions = conv_qs.count()
        conversion_rate = round((total_conversions / total * 100), 1) if total > 0 else 0
        total_conversion_value = sum(c.event_value for c in conv_qs.only('event_value') if c.event_value)
        conversion_by_type = list(
            conv_qs.values('event_type')
            .annotate(count=DjCount('id')).order_by('-count')
        )
        conversion_daily_raw = list(
            conv_qs.annotate(day=TruncDate('created_at'))
            .values('day').annotate(count=DjCount('id')).order_by('day')
        )
        conv_by_day = {str(row['day']): row['count'] for row in conversion_daily_raw}
        conversion_daily = []
        for i in range(period_days):
            d = (today - timedelta(days=period_days - 1 - i))
            conversion_daily.append({'date': str(d), 'conversions': conv_by_day.get(str(d), 0)})

        return Response({
            'qr_id': str(qr.id),
            'slug': qr.slug,
            'name': qr.title,
            'total_scans': total,
            'unique_scans': unique,
            'period_days': period_days,
            'top_countries': country_breakdown,
            'top_devices': device_breakdown,
            'browser_breakdown': browser_breakdown,
            'os_breakdown': os_breakdown,
            'hourly_breakdown': hourly_breakdown,
            'referrer_breakdown': referrer_breakdown,
            'daily_trend': daily_trend,
            # Conversion data
            'total_conversions': total_conversions,
            'conversion_rate': conversion_rate,
            'total_conversion_value': total_conversion_value,
            'conversion_by_type': conversion_by_type,
            'conversion_daily': conversion_daily,
        })


class ScanEventListView(APIView):
    """
    GET /api/v1/analytics/events/?qr=<id>&page=1
    Paginated raw scan events.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.qrcodes.models import QRCode
        qr_id = request.query_params.get('qr')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))

        qs = ScanEvent.objects.select_related('qr_code')
        if qr_id:
            try:
                qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
                qs = qs.filter(qr_code=qr)
            except QRCode.DoesNotExist:
                return Response([])
        else:
            user_qr_ids = QRCode.objects.filter(organization=request.user.organization).values_list('id', flat=True)
            qs = qs.filter(qr_code_id__in=user_qr_ids)

        total = qs.count()
        start = (page - 1) * page_size
        events = qs[start:start + page_size]
        serializer = ScanEventSerializer(events, many=True)
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class DailyMetricListView(APIView):
    """
    GET /api/v1/analytics/daily/?qr=<id>
    Pre-aggregated daily metric rows.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.qrcodes.models import QRCode
        qr_id = request.query_params.get('qr')
        days = int(request.query_params.get('days', 30))
        cutoff = timezone.now().date() - timedelta(days=days)

        if qr_id:
            try:
                qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
                qs = DailyMetric.objects.filter(qr_code=qr, date__gte=cutoff)
            except QRCode.DoesNotExist:
                return Response([])
        else:
            user_qr_ids = QRCode.objects.filter(organization=request.user.organization).values_list('id', flat=True)
            qs = DailyMetric.objects.filter(qr_code_id__in=user_qr_ids, date__gte=cutoff)

        serializer = DailyMetricSerializer(qs.order_by('-date'), many=True)
        return Response(serializer.data)


class LinkClickTrackView(APIView):
    """
    POST /api/v1/analytics/click/
    Body: { qr_id, link_url, link_label }
    Records a click on an individual link within a multi-link QR.
    No auth required — called from public landing pages via sendBeacon.
    """
    permission_classes = []

    def post(self, request):
        from apps.qrcodes.models import QRCode
        from apps.core.utils import get_client_ip

        qr_id = request.data.get('qr_id')
        link_url = request.data.get('link_url', '')
        link_label = request.data.get('link_label', '')

        if not qr_id or not link_url:
            return Response({'error': 'qr_id and link_url required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            qr = QRCode.objects.get(id=qr_id)
        except QRCode.DoesNotExist:
            return Response({'error': 'QR not found.'}, status=status.HTTP_404_NOT_FOUND)

        ip = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')
        ua_lower = ua.lower()
        device_type = 'mobile' if any(m in ua_lower for m in ['mobile', 'android', 'iphone']) else 'desktop'

        country = ''
        try:
            from urllib.request import urlopen, Request
            import json
            if ip and not any(ip.startswith(p) for p in ('127.', '10.', '192.168.')):
                req = Request(f"https://ipinfo.io/{ip}/json", headers={'User-Agent': 'QRGenie/1.0'})
                with urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode())
                country = data.get('country', '')
        except Exception:
            pass

        LinkClickEvent.objects.create(
            qr_code=qr,
            link_url=link_url[:2048],
            link_label=link_label[:255],
            ip_address=ip,
            country=country,
            device_type=device_type,
        )

        # Also increment click_count on matching MultiLinkItem (best-effort)
        try:
            from apps.qrcodes.models import MultiLinkItem
            from django.db.models import F as DbF
            MultiLinkItem.objects.filter(
                qr_code=qr, url=link_url[:2048]
            ).update(click_count=DbF('click_count') + 1)
        except Exception:
            pass

        return Response({'ok': True})


class LinkClickAnalyticsView(APIView):
    """
    GET /api/v1/analytics/qr/<qr_id>/link-clicks/?period=30
    Returns aggregated link-click analytics for a QR code.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, qr_id):
        from apps.qrcodes.models import QRCode, MultiLinkItem
        from django.db.models import Count as DjCount
        from django.db.models.functions import TruncDate as DjTruncDate

        try:
            qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
        except QRCode.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        period_days = int(request.query_params.get('period', 30))
        cutoff = timezone.now() - timedelta(days=period_days)
        qs = LinkClickEvent.objects.filter(qr_code=qr, clicked_at__gte=cutoff)

        total_clicks = qs.count()

        # Per-link breakdown
        per_link = list(
            qs.values('link_url', 'link_label')
            .annotate(clicks=DjCount('id'))
            .order_by('-clicks')[:50]
        )

        # Daily trend (all links combined)
        daily_raw = list(
            qs.annotate(day=DjTruncDate('clicked_at'))
            .values('day').annotate(clicks=DjCount('id')).order_by('day')
        )
        click_by_day = {str(row['day']): row['clicks'] for row in daily_raw}
        today = timezone.now().date()
        daily_trend = []
        for i in range(period_days):
            d = today - timedelta(days=period_days - 1 - i)
            daily_trend.append({'date': str(d), 'clicks': click_by_day.get(str(d), 0)})

        # Per-link daily breakdown (top 10 links only)
        top_urls = [item['link_url'] for item in per_link[:10]]
        per_link_daily = {}
        if top_urls:
            for url in top_urls:
                link_daily_raw = list(
                    qs.filter(link_url=url)
                    .annotate(day=DjTruncDate('clicked_at'))
                    .values('day').annotate(clicks=DjCount('id')).order_by('day')
                )
                by_day = {str(row['day']): row['clicks'] for row in link_daily_raw}
                per_link_daily[url] = [
                    {'date': str(today - timedelta(days=period_days - 1 - i)),
                     'clicks': by_day.get(str(today - timedelta(days=period_days - 1 - i)), 0)}
                    for i in range(period_days)
                ]

        # Device breakdown for link clicks
        device_breakdown = list(
            qs.exclude(device_type='').values('device_type')
            .annotate(clicks=DjCount('id')).order_by('-clicks')
        )

        # Country breakdown for link clicks
        country_breakdown = list(
            qs.exclude(country='').values('country')
            .annotate(clicks=DjCount('id')).order_by('-clicks')[:10]
        )

        # Multi-link items with their stored click counts
        multi_links = list(
            MultiLinkItem.objects.filter(qr_code=qr, is_active=True)
            .order_by('sort_order')
            .values('id', 'title', 'url', 'click_count', 'sort_order')
        )
        for ml in multi_links:
            ml['id'] = str(ml['id'])

        return Response({
            'qr_id': str(qr.id),
            'period_days': period_days,
            'total_clicks': total_clicks,
            'per_link': per_link,
            'daily_trend': daily_trend,
            'per_link_daily': per_link_daily,
            'device_breakdown': device_breakdown,
            'country_breakdown': country_breakdown,
            'multi_links': multi_links,
        })


class ConversionTrackView(APIView):
    """
    POST /api/v1/analytics/conversion/
    Body: { qr_id, event_type, event_label?, event_value?, metadata?, session_id? }
    Records a conversion event. No auth — called from public pages via sendBeacon.
    """
    permission_classes = []

    def post(self, request):
        from apps.qrcodes.models import QRCode
        from apps.core.utils import get_client_ip

        qr_id = request.data.get('qr_id')
        event_type = request.data.get('event_type', '')

        if not qr_id or not event_type:
            return Response({'error': 'qr_id and event_type required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            qr = QRCode.objects.get(id=qr_id)
        except QRCode.DoesNotExist:
            return Response({'error': 'QR not found.'}, status=status.HTTP_404_NOT_FOUND)

        ip = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')
        ua_lower = ua.lower()
        device_type = 'mobile' if any(m in ua_lower for m in ['mobile', 'android', 'iphone']) else 'desktop'

        country = ''
        try:
            from django.core.cache import cache
            cache_key = f"geoip:{ip}"
            cached = cache.get(cache_key)
            if cached:
                country = cached[0] if isinstance(cached, (list, tuple)) else ''
            elif ip and not any(ip.startswith(p) for p in ('127.', '10.', '192.168.', '::1')):
                from urllib.request import urlopen, Request
                import json
                req = Request(f"https://ipinfo.io/{ip}/json", headers={'User-Agent': 'QRGenie/1.0'})
                with urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode())
                country = data.get('country', '')
        except Exception:
            pass

        event_value = request.data.get('event_value', 0)
        try:
            event_value = float(event_value)
        except (TypeError, ValueError):
            event_value = 0

        ConversionEvent.objects.create(
            qr_code=qr,
            event_type=event_type[:50],
            event_label=(request.data.get('event_label', '') or '')[:255],
            event_value=event_value,
            metadata=request.data.get('metadata', {}) or {},
            ip_address=ip,
            country=country,
            device_type=device_type,
            user_agent=ua[:500],
            session_id=(request.data.get('session_id', '') or '')[:64],
        )

        return Response({'ok': True}, status=status.HTTP_201_CREATED)


class ConversionAnalyticsView(APIView):
    """
    GET /api/v1/analytics/qr/<qr_id>/conversions/?period=30
    Detailed conversion analytics for a specific QR code.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, qr_id):
        from apps.qrcodes.models import QRCode
        from django.db.models import Count as DjCount, Sum as DjSum

        try:
            qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
        except QRCode.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        period_days = int(request.query_params.get('period', 30))
        cutoff = timezone.now() - timedelta(days=period_days)
        qs = ConversionEvent.objects.filter(qr_code=qr, created_at__gte=cutoff)

        total = qs.count()
        total_value = qs.aggregate(total=DjSum('event_value'))['total'] or 0

        # Scans in same period for conversion rate
        scan_count = ScanEvent.objects.filter(qr_code=qr, scanned_at__gte=cutoff).count()
        conversion_rate = round((total / scan_count * 100), 1) if scan_count > 0 else 0

        by_type = list(
            qs.values('event_type')
            .annotate(count=DjCount('id'), value=DjSum('event_value'))
            .order_by('-count')
        )

        daily_raw = list(
            qs.annotate(day=TruncDate('created_at'))
            .values('day').annotate(count=DjCount('id'), value=DjSum('event_value')).order_by('day')
        )
        conv_by_day = {str(r['day']): {'count': r['count'], 'value': float(r['value'] or 0)} for r in daily_raw}
        today = timezone.now().date()
        daily_trend = []
        for i in range(period_days):
            d = today - timedelta(days=period_days - 1 - i)
            entry = conv_by_day.get(str(d), {'count': 0, 'value': 0})
            daily_trend.append({'date': str(d), 'conversions': entry['count'], 'value': entry['value']})

        recent = ConversionEventSerializer(qs[:20], many=True).data

        return Response({
            'qr_id': str(qr.id),
            'period_days': period_days,
            'total_conversions': total,
            'total_value': float(total_value),
            'conversion_rate': conversion_rate,
            'scan_count': scan_count,
            'by_type': by_type,
            'daily_trend': daily_trend,
            'recent_events': recent,
        })
