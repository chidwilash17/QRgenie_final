"""
Analytics Celery Tasks — scan recording, daily aggregation, exports
=====================================================================
"""
import hashlib
from datetime import timedelta, date
from celery import shared_task
from django.utils import timezone
from django.db.models import Count, F


@shared_task(queue='analytics', ignore_result=True, max_retries=3)
def record_scan_event(
    qr_id: str,
    ip_address: str,
    user_agent: str,
    device_type: str = 'unknown',
    os: str = 'unknown',
    browser: str = 'unknown',
    country: str = '',
    city: str = '',
    language: str = '',
    referrer: str = '',
    latitude: float = None,
    longitude: float = None,
    destination_url: str = '',
    rule_matched: str = None,
):
    """
    Record a scan event asynchronously.
    Called from redirect engine after every QR scan.
    """
    from apps.analytics.models import ScanEvent
    from apps.qrcodes.models import QRCode

    try:
        qr = QRCode.objects.get(id=qr_id)
    except QRCode.DoesNotExist:
        return

    # Build a fingerprint for unique detection (IP + UA + QR + date)
    today = timezone.now().date().isoformat()
    raw_fp = f"{ip_address}:{user_agent}:{qr_id}:{today}"
    fingerprint = hashlib.sha256(raw_fp.encode()).hexdigest()

    # Skip if already recorded by direct DB write (avoids duplicate rows)
    if ScanEvent.objects.filter(qr_code=qr, fingerprint=fingerprint).exists():
        return

    is_unique = True  # First time this fingerprint is seen — it's unique

    ScanEvent.objects.create(
        qr_code=qr,
        ip_address=ip_address,
        country=country or '',
        city=city or '',
        device_type=device_type,
        os=os,
        browser=browser,
        language=language,
        user_agent=user_agent[:512] if user_agent else '',
        referrer=referrer[:1024] if referrer else '',
        latitude=latitude,
        longitude=longitude,
        destination_url=destination_url[:2048] if destination_url else '',
        rule_matched=rule_matched,
        fingerprint=fingerprint,
        is_unique=is_unique,
    )

    # Update counters on QR code
    QRCode.objects.filter(id=qr_id).update(total_scans=F('total_scans') + 1)
    if is_unique:
        QRCode.objects.filter(id=qr_id).update(unique_scans=F('unique_scans') + 1)


@shared_task(queue='analytics', ignore_result=True)
def aggregate_daily_metrics(target_date: str = None):
    """
    Aggregate scan events into DailyMetric rows.
    Run nightly via celery-beat.
    If target_date is None, aggregates yesterday.
    """
    from apps.analytics.models import ScanEvent, DailyMetric
    from apps.qrcodes.models import QRCode

    if target_date:
        d = date.fromisoformat(target_date)
    else:
        d = (timezone.now() - timedelta(days=1)).date()

    # Get all QR codes that had scans on this date
    qr_ids = (
        ScanEvent.objects
        .filter(scanned_at__date=d)
        .values_list('qr_code_id', flat=True)
        .distinct()
    )

    for qr_id in qr_ids:
        scans = ScanEvent.objects.filter(qr_code_id=qr_id, scanned_at__date=d)

        total = scans.count()
        unique = scans.filter(is_unique=True).count()

        # Build breakdowns
        country_breakdown = dict(
            scans.values_list('country').annotate(c=Count('id')).values_list('country', 'c')
        )
        device_breakdown = dict(
            scans.values_list('device_type').annotate(c=Count('id')).values_list('device_type', 'c')
        )
        browser_breakdown = dict(
            scans.values_list('browser').annotate(c=Count('id')).values_list('browser', 'c')
        )
        os_breakdown = dict(
            scans.values_list('os').annotate(c=Count('id')).values_list('os', 'c')
        )

        # Hourly breakdown
        hourly = {}
        for scan in scans.values('scanned_at'):
            h = str(scan['scanned_at'].hour)
            hourly[h] = hourly.get(h, 0) + 1

        # Referrer breakdown
        referrer_breakdown = dict(
            scans.exclude(referrer='').values_list('referrer').annotate(c=Count('id')).values_list('referrer', 'c')
        )

        # Link clicks count
        from apps.analytics.models import LinkClickEvent
        link_clicks = LinkClickEvent.objects.filter(qr_code_id=qr_id, clicked_at__date=d).count()

        DailyMetric.objects.update_or_create(
            qr_code_id=qr_id,
            date=d,
            defaults={
                'total_scans': total,
                'unique_scans': unique,
                'country_breakdown': country_breakdown,
                'device_breakdown': device_breakdown,
                'browser_breakdown': browser_breakdown,
                'os_breakdown': os_breakdown,
                'hourly_breakdown': hourly,
                'referrer_breakdown': referrer_breakdown,
                'link_clicks': link_clicks,
            },
        )


@shared_task(queue='analytics', ignore_result=True)
def export_analytics_csv(org_id: str, qr_id: str = None, period_days: int = 30):
    """
    Export scan events to CSV and store in media/exports/.
    Returns path to the generated file.
    """
    import csv
    import os
    from django.conf import settings
    from apps.analytics.models import ScanEvent

    start = timezone.now() - timedelta(days=period_days)
    qs = ScanEvent.objects.filter(
        qr_code__organization_id=org_id,
        scanned_at__gte=start,
    ).select_related('qr_code')

    if qr_id:
        qs = qs.filter(qr_code_id=qr_id)

    exports_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    os.makedirs(exports_dir, exist_ok=True)

    filename = f"scans_{org_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(exports_dir, filename)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Scan ID', 'QR Code', 'QR Slug', 'Scanned At',
            'IP', 'Country', 'City', 'Device', 'OS', 'Browser',
            'Language', 'Referrer', 'Destination URL', 'Is Unique',
        ])
        for scan in qs.iterator(chunk_size=1000):
            writer.writerow([
                str(scan.id), scan.qr_code.title, scan.qr_code.slug,
                scan.scanned_at.isoformat(),
                scan.ip_address, scan.country, scan.city,
                scan.device_type, scan.os, scan.browser,
                scan.language, scan.referrer, scan.destination_url,
                scan.is_unique,
            ])

    return f"exports/{filename}"
