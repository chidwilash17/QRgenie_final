"""
AI Service — Celery Tasks
============================
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('qrgenie')


@shared_task(queue='ai', bind=True, max_retries=2)
def generate_landing_page(self, qr_id: str = None, prompt: str = '', org_id: str = None, user_id: str = None):
    """
    Generate an AI landing page for a QR code.
    Creates a LandingPage record and updates the QR code.
    """
    from apps.ai_service.models import AIGenerationLog
    from apps.ai_service.client import generate_landing_page_html
    from apps.qrcodes.models import QRCode

    try:
        qr = QRCode.objects.get(id=qr_id) if qr_id else None
    except QRCode.DoesNotExist:
        qr = None

    _org_id = org_id or (str(qr.organization_id) if qr else None)
    log = AIGenerationLog.objects.create(
        organization_id=_org_id,
        user_id=user_id,
        generation_type='landing_page',
        status='processing',
        prompt=prompt or f"Generate a landing page for: {qr.title if qr else 'QR Code'}",
        qr_code=qr,
    )

    try:
        result = generate_landing_page_html(
            business_name=qr.title if qr else 'My Business',
            business_type=qr.metadata.get('business_type', 'general') if qr else 'general',
            description=qr.description if qr else prompt,
            links=[],
            style='modern',
            color_scheme=qr.foreground_color if qr else '#6366f1',
        )

        # Create landing page record
        from apps.landing_pages.models import LandingPage
        page = LandingPage.objects.create(
            organization_id=_org_id,
            qr_code=qr,
            title=result.get('title', qr.title if qr else 'Landing Page'),
            slug=qr.slug if qr else '',
            html_content=result.get('html', ''),
            meta_description=result.get('meta_description', ''),
            is_ai_generated=True,
            is_published=True,
        )

        log.status = 'completed'
        log.result = {'landing_page_id': str(page.id), 'title': page.title}
        log.total_tokens = result.get('tokens_used', 0)
        log.completed_at = timezone.now()
        log.save()

        return {'landing_page_id': str(page.id), 'status': 'completed'}

    except Exception as e:
        log.status = 'failed'
        log.error_message = str(e)
        log.save()
        logger.error(f"AI landing page generation failed: {e}")
        raise self.retry(exc=e, countdown=30)


@shared_task(queue='ai', bind=True, max_retries=2)
def generate_analytics_summary_task(self, qr_id: str, org_id: str, user_id: str = None):
    """Generate AI-powered analytics summary for a QR code."""
    from apps.ai_service.models import AIGenerationLog
    from apps.ai_service.client import generate_analytics_summary
    from apps.analytics.models import ScanEvent, DailyMetric

    log = AIGenerationLog.objects.create(
        organization_id=org_id,
        user_id=user_id,
        generation_type='analytics_summary',
        status='processing',
        prompt=f'Analytics summary for QR {qr_id}',
        qr_code_id=qr_id,
    )

    try:
        from datetime import timedelta
        scans = ScanEvent.objects.filter(qr_code_id=qr_id).order_by('-scanned_at')
        total = scans.count()
        unique = scans.filter(is_unique=True).count()

        from django.db.models import Count
        countries = list(scans.values('country').annotate(c=Count('id')).order_by('-c')[:10])
        devices = list(scans.values('device_type').annotate(c=Count('id')).order_by('-c'))

        analytics_data = {
            'total_scans': total,
            'unique_scans': unique,
            'top_countries': countries,
            'top_devices': devices,
        }

        result = generate_analytics_summary(analytics_data)

        log.status = 'completed'
        log.result = result
        log.total_tokens = result.get('tokens_used', 0)
        log.completed_at = timezone.now()
        log.save()

        return result

    except Exception as e:
        log.status = 'failed'
        log.error_message = str(e)
        log.save()
        raise self.retry(exc=e, countdown=30)


@shared_task(queue='ai', bind=True, max_retries=1)
def optimize_routing(self, qr_id: str):
    """AI-powered routing optimization based on scan patterns."""
    from apps.ai_service.client import suggest_smart_routing
    from apps.qrcodes.models import QRCode
    from apps.analytics.models import ScanEvent

    try:
        qr = QRCode.objects.get(id=qr_id)
    except QRCode.DoesNotExist:
        return {'error': 'QR not found'}

    scans = ScanEvent.objects.filter(qr_code=qr).order_by('-scanned_at')[:100]
    scan_data = [
        {'country': s.country, 'device': s.device_type, 'os': s.os, 'browser': s.browser, 'time': str(s.scanned_at)}
        for s in scans
    ]

    qr_data = {
        'title': qr.title,
        'type': qr.qr_type,
        'destination': qr.destination_url,
        'total_scans': qr.total_scans,
    }

    return suggest_smart_routing(qr_data, scan_data)
