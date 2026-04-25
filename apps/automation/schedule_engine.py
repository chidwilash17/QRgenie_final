"""
Automation — Schedule Execution Engine
========================================
Handles scheduled QR behavior changes, cron computation, and external hook delivery.
"""
import logging
import json
import hashlib
import hmac as hmac_mod
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger('qrgenie')


def compute_next_run(schedule) -> timezone.datetime:
    """Compute the next execution time for a QRSchedule."""
    now = timezone.now()

    if schedule.repeat == 'once':
        return schedule.scheduled_at if schedule.scheduled_at and schedule.scheduled_at > now else None

    if schedule.repeat == 'daily':
        base = schedule.last_run_at or now
        next_dt = base + timedelta(days=1)
        return next_dt if next_dt > now else now + timedelta(minutes=1)

    if schedule.repeat == 'weekly':
        base = schedule.last_run_at or now
        next_dt = base + timedelta(weeks=1)
        return next_dt if next_dt > now else now + timedelta(minutes=1)

    if schedule.repeat == 'monthly':
        base = schedule.last_run_at or now
        month = base.month % 12 + 1
        year = base.year + (1 if month == 1 else 0)
        try:
            next_dt = base.replace(year=year, month=month)
        except ValueError:
            next_dt = base.replace(year=year, month=month, day=28)
        return next_dt if next_dt > now else now + timedelta(minutes=1)

    if schedule.repeat == 'cron' and schedule.cron_expression:
        try:
            from croniter import croniter
            cron = croniter(schedule.cron_expression, now)
            return cron.get_next(timezone.datetime)
        except Exception:
            # croniter not available — fall back to 1 hour
            return now + timedelta(hours=1)

    return None


def execute_schedule(schedule) -> tuple:
    """
    Execute a single QRSchedule action. Returns (success: bool, message: str).
    """
    from apps.qrcodes.models import QRCode
    from .models import QRScheduleLog

    try:
        qr = QRCode.objects.get(id=schedule.qr_code_id)
    except QRCode.DoesNotExist:
        QRScheduleLog.objects.create(
            schedule=schedule, status='failed',
            error_message='QR code not found',
        )
        return False, 'QR code not found'

    action = schedule.action
    payload = schedule.payload or {}
    details = {'action': action, 'qr_id': str(qr.id), 'qr_slug': qr.slug}

    try:
        if action == 'activate':
            qr.status = 'active'
            qr.save(update_fields=['status', 'updated_at'])
            details['new_status'] = 'active'

        elif action == 'pause':
            qr.status = 'paused'
            qr.save(update_fields=['status', 'updated_at'])
            details['new_status'] = 'paused'

        elif action == 'expire':
            qr.status = 'expired'
            qr.save(update_fields=['status', 'updated_at'])
            details['new_status'] = 'expired'

        elif action == 'change_url':
            new_url = payload.get('url', '')
            if not new_url:
                raise ValueError('No URL provided in payload')
            details['old_url'] = qr.destination_url
            qr.destination_url = new_url
            qr.save(update_fields=['destination_url', 'updated_at'])
            details['new_url'] = new_url

        elif action == 'change_fallback':
            new_url = payload.get('url', '')
            if not new_url:
                raise ValueError('No fallback URL provided in payload')
            details['old_url'] = qr.fallback_url
            qr.fallback_url = new_url
            qr.save(update_fields=['fallback_url', 'updated_at'])
            details['new_url'] = new_url

        elif action == 'rotate_page':
            _rotate_to_next_page(qr)
            details['rotated'] = True

        else:
            raise ValueError(f'Unknown action: {action}')

        # Log success
        QRScheduleLog.objects.create(
            schedule=schedule, status='success', details=details,
        )

        # Update schedule counters
        schedule.total_runs += 1
        schedule.last_run_at = timezone.now()
        schedule.next_run_at = compute_next_run(schedule)
        schedule.save(update_fields=['total_runs', 'last_run_at', 'next_run_at'])

        # Deactivate one-time schedules
        if schedule.repeat == 'once':
            schedule.is_active = False
            schedule.save(update_fields=['is_active'])

        # Fire external hooks
        fire_external_hooks(
            event_type='schedule.executed',
            payload={
                'event': 'schedule.executed',
                'schedule_id': str(schedule.id),
                'schedule_name': schedule.name,
                **details,
            },
            org_id=str(schedule.organization_id),
        )

        return True, f'Schedule "{schedule.name}" executed successfully'

    except Exception as e:
        QRScheduleLog.objects.create(
            schedule=schedule, status='failed',
            error_message=str(e), details=details,
        )
        logger.error(f"Schedule execution failed: {schedule.id} - {e}")
        return False, str(e)


def _rotate_to_next_page(qr):
    """Advance the QR code's rotation schedule to the next page."""
    try:
        rotation = qr.rotation_schedule
        if not rotation or not rotation.pages:
            raise ValueError('No rotation schedule configured')

        # Find current URL in pages list and advance to next
        pages = rotation.pages
        current = qr.destination_url
        current_idx = -1
        for i, page in enumerate(pages):
            if page.get('page_url') == current:
                current_idx = i
                break

        next_idx = (current_idx + 1) % len(pages)
        new_url = pages[next_idx].get('page_url', '')
        if new_url:
            qr.destination_url = new_url
            qr.save(update_fields=['destination_url', 'updated_at'])

    except Exception as e:
        raise ValueError(f'Rotation failed: {e}')


def process_due_schedules():
    """
    Find and execute all due schedules. Called by management command.
    """
    from .models import QRSchedule
    now = timezone.now()

    due = QRSchedule.objects.filter(
        is_active=True,
        next_run_at__lte=now,
    ).select_related('qr_code')

    count = 0
    for schedule in due:
        success, msg = execute_schedule(schedule)
        count += 1
        logger.info(f"Schedule {schedule.id}: {'OK' if success else 'FAIL'} — {msg}")

    return count


def fire_external_hooks(event_type: str, payload: dict, org_id: str):
    """
    Fire all active external hook subscriptions (n8n/Zapier) for an event.
    """
    import httpx
    from .models import ExternalHookSubscription

    subs = ExternalHookSubscription.objects.filter(
        organization_id=org_id,
        event=event_type,
        is_active=True,
    )

    for sub in subs:
        try:
            body = json.dumps(payload, default=str)
            headers = {
                'Content-Type': 'application/json',
                'X-QRGenie-Event': event_type,
                'X-QRGenie-Hook-Id': str(sub.id),
                'User-Agent': 'QRGenie-Hooks/1.0',
            }
            resp = httpx.post(sub.target_url, content=body, headers=headers, timeout=10)

            if 200 <= resp.status_code < 300:
                sub.consecutive_failures = 0
                sub.save(update_fields=['consecutive_failures'])
            else:
                raise Exception(f"HTTP {resp.status_code}")

        except Exception as e:
            sub.consecutive_failures += 1
            sub.last_failure_at = timezone.now()
            if sub.consecutive_failures >= 10:
                sub.is_active = False
            sub.save(update_fields=['consecutive_failures', 'last_failure_at', 'is_active'])
            logger.warning(f"External hook delivery failed: {sub.id} - {e}")
