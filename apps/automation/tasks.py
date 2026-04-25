"""
Automation Engine — Celery Tasks & Execution Engine
======================================================
"""
import time
import hashlib
import logging
import httpx
from celery import shared_task
from django.utils import timezone
from django.conf import settings


logger = logging.getLogger('qrgenie')


@shared_task(queue='automation', ignore_result=True, max_retries=2)
def fire_automation_trigger(trigger_type: str, context: dict, org_id: str = None, qr_id: str = None):
    """
    Main entry point: finds matching automations for a trigger event and executes them.
    Called from signals or other tasks when events occur.
    """
    from apps.automation.models import Automation

    filters = {
        'trigger_type': trigger_type,
        'status': 'active',
    }
    if org_id:
        filters['organization_id'] = org_id
    if qr_id:
        filters['qr_code_id'] = qr_id

    # Also get automations with no QR filter (org-wide triggers)
    automations = Automation.objects.filter(**filters)
    if qr_id and org_id:
        automations = automations | Automation.objects.filter(
            trigger_type=trigger_type,
            status='active',
            organization_id=org_id,
            qr_code__isnull=True,
        )

    for automation in automations.distinct():
        try:
            execute_automation.delay(str(automation.id), context)
        except Exception:
            # Broker unavailable — run synchronously
            _execute_automation_core(str(automation.id), context)


def _execute_automation_core(automation_id: str, context: dict):
    """
    Core automation execution logic — plain function, no Celery dependency.
    """
    from apps.automation.models import Automation, AutomationRun, AutomationActionLog

    try:
        automation = Automation.objects.prefetch_related('conditions', 'actions').get(id=automation_id)
    except Automation.DoesNotExist:
        return

    # Create run record
    run = AutomationRun.objects.create(
        automation=automation,
        status='running',
        trigger_data=context,
    )
    start = time.time()

    try:
        # Evaluate all conditions (AND logic)
        for condition in automation.conditions.all():
            if not condition.evaluate(context):
                run.status = 'skipped'
                run.completed_at = timezone.now()
                run.duration_ms = int((time.time() - start) * 1000)
                run.save()
                return

        # Execute actions in order
        all_success = True
        for action in automation.actions.all():
            action_start = time.time()
            try:
                result = _execute_action(action, context, automation)
                AutomationActionLog.objects.create(
                    run=run,
                    action=action,
                    status='success',
                    input_data={'action_type': action.action_type, 'config': action.config},
                    output_data=result or {},
                    duration_ms=int((time.time() - action_start) * 1000),
                )
            except Exception as e:
                all_success = False
                AutomationActionLog.objects.create(
                    run=run,
                    action=action,
                    status='failed',
                    input_data={'action_type': action.action_type, 'config': action.config},
                    error_message=str(e),
                    duration_ms=int((time.time() - action_start) * 1000),
                )
                logger.error(f"Automation action failed: {automation.id}/{action.id} - {e}")

        run.status = 'success' if all_success else 'partial'
        run.completed_at = timezone.now()
        run.duration_ms = int((time.time() - start) * 1000)
        run.save()

        # Update automation counters
        automation.total_runs += 1
        automation.last_run_at = timezone.now()
        automation.save(update_fields=['total_runs', 'last_run_at'])

    except Exception as e:
        run.status = 'failed'
        run.error_message = str(e)
        run.completed_at = timezone.now()
        run.duration_ms = int((time.time() - start) * 1000)
        run.save()
        logger.error(f"Automation execution failed: {automation.id} - {e}")


@shared_task(queue='automation', bind=True, max_retries=3)
def execute_automation(self, automation_id: str, context: dict):
    """
    Celery wrapper — delegates to core logic, adds retry support.
    """
    try:
        _execute_automation_core(automation_id, context)
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


def _execute_action(action, context: dict, automation) -> dict:
    """Dispatch to the correct action handler."""
    handlers = {
        'send_email': _action_send_email,
        'send_sms': _action_send_sms,
        'send_whatsapp': _action_send_whatsapp,
        'send_slack': _action_send_slack,
        'send_teams': _action_send_teams,
        'webhook': _action_webhook,
        'update_qr': _action_update_qr,
        'pause_qr': _action_pause_qr,
        'activate_qr': _action_activate_qr,
        'ai_generate_page': _action_ai_generate_page,
        'ai_optimize_route': _action_ai_optimize_route,
    }
    handler = handlers.get(action.action_type)
    if not handler:
        raise ValueError(f"Unknown action type: {action.action_type}")
    return handler(action.config, context, automation)


# ─── Action Handlers ──────────────────────────────────────────────────────────


def _action_send_email(config: dict, context: dict, automation) -> dict:
    """Send email via Django's configured SMTP backend."""
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    to = config.get('to', '')
    if not to:
        raise ValueError('No recipient email address configured')

    subject = config.get('subject', f'QRGenie Automation: {automation.name}')
    body = config.get('body', '')

    # If no body provided, build a default summary
    if not body:
        lines = [f'<h2>Automation Triggered: {automation.name}</h2>']
        lines.append(f'<p><strong>Trigger:</strong> {automation.trigger_type}</p>')
        if context:
            lines.append('<h3>Event Data:</h3><ul>')
            for key, val in context.items():
                lines.append(f'<li><strong>{key}:</strong> {val}</li>')
            lines.append('</ul>')
        body = '\n'.join(lines)

    # Template variable substitution
    for key, val in context.items():
        body = body.replace(f'{{{{{key}}}}}', str(val))
        subject = subject.replace(f'{{{{{key}}}}}', str(val))

    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@qrgenie.io')

    logger.info(f"[Email Action] Sending to={to}, subject={subject}, from={from_email}")
    logger.info(f"[Email Action] EMAIL_HOST={getattr(django_settings, 'EMAIL_HOST', 'NOT SET')}, "
                f"EMAIL_PORT={getattr(django_settings, 'EMAIL_PORT', 'NOT SET')}, "
                f"EMAIL_USE_TLS={getattr(django_settings, 'EMAIL_USE_TLS', 'NOT SET')}")

    try:
        sent = send_mail(
            subject=subject,
            message='',
            html_message=body,
            from_email=from_email,
            recipient_list=[to],
            fail_silently=False,
        )
        logger.info(f"[Email Action] send_mail returned: {sent}")
        return {'sent': sent, 'to': to, 'subject': subject}
    except Exception as e:
        logger.error(f"[Email Action] SMTP FAILED: {type(e).__name__}: {e}")
        raise


def _action_send_sms(config: dict, context: dict, automation) -> dict:
    """Send SMS via Twilio."""
    from decouple import config as env_config
    account_sid = env_config('TWILIO_ACCOUNT_SID', default='')
    auth_token = env_config('TWILIO_AUTH_TOKEN', default='')
    from_number = env_config('TWILIO_FROM_NUMBER', default='')

    if not all([account_sid, auth_token, from_number]):
        raise ValueError('Twilio credentials not configured')

    to = config.get('to', '')
    message = config.get('message', '')
    for key, val in context.items():
        message = message.replace(f'{{{{{key}}}}}', str(val))

    response = httpx.post(
        f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json',
        auth=(account_sid, auth_token),
        data={'From': from_number, 'To': to, 'Body': message},
        timeout=15,
    )
    return {'status_code': response.status_code}


def _action_send_whatsapp(config: dict, context: dict, automation) -> dict:
    """Send WhatsApp message via Twilio WhatsApp API."""
    from decouple import config as env_config
    account_sid = env_config('TWILIO_ACCOUNT_SID', default='')
    auth_token = env_config('TWILIO_AUTH_TOKEN', default='')
    from_number = env_config('TWILIO_WHATSAPP_FROM', default='')

    to = config.get('to', '')
    message = config.get('message', '')
    for key, val in context.items():
        message = message.replace(f'{{{{{key}}}}}', str(val))

    response = httpx.post(
        f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json',
        auth=(account_sid, auth_token),
        data={'From': f'whatsapp:{from_number}', 'To': f'whatsapp:{to}', 'Body': message},
        timeout=15,
    )
    return {'status_code': response.status_code}


def _action_send_slack(config: dict, context: dict, automation) -> dict:
    """Send Slack notification via incoming webhook."""
    webhook_url = config.get('webhook_url', '')
    message = config.get('message', '')
    for key, val in context.items():
        message = message.replace(f'{{{{{key}}}}}', str(val))

    response = httpx.post(webhook_url, json={'text': message}, timeout=10)
    return {'status_code': response.status_code}


def _action_send_teams(config: dict, context: dict, automation) -> dict:
    """Send MS Teams notification via incoming webhook."""
    webhook_url = config.get('webhook_url', '')
    message = config.get('message', '')
    for key, val in context.items():
        message = message.replace(f'{{{{{key}}}}}', str(val))

    response = httpx.post(webhook_url, json={
        '@type': 'MessageCard',
        'summary': f'QRGenie: {automation.name}',
        'text': message,
    }, timeout=10)
    return {'status_code': response.status_code}


def _action_webhook(config: dict, context: dict, automation) -> dict:
    """Call an external webhook URL."""
    url = config.get('url', '')
    method = config.get('method', 'POST').upper()
    headers = config.get('headers', {})
    include_context = config.get('include_context', True)

    # Add HMAC signature for verification
    secret = config.get('secret', '')
    payload = context if include_context else {}

    import json
    body = json.dumps(payload, default=str)

    if secret:
        import hmac
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers['X-QRGenie-Signature'] = f'sha256={sig}'

    headers.setdefault('Content-Type', 'application/json')

    response = httpx.request(method, url, headers=headers, content=body, timeout=15)
    return {'status_code': response.status_code, 'body_preview': response.text[:500]}


def _action_update_qr(config: dict, context: dict, automation) -> dict:
    """Update a field on the QR code."""
    from apps.qrcodes.models import QRCode

    qr_id = context.get('qr_id') or (str(automation.qr_code_id) if automation.qr_code_id else None)
    if not qr_id:
        raise ValueError('No QR code ID available')

    qr = QRCode.objects.get(id=qr_id)
    field = config.get('field', '')
    value = config.get('value', '')

    allowed_fields = ['destination_url', 'fallback_url', 'title', 'description', 'status']
    if field not in allowed_fields:
        raise ValueError(f'Field {field} not allowed for update')

    setattr(qr, field, value)
    qr.save(update_fields=[field, 'updated_at'])

    return {'qr_id': str(qr.id), 'field': field, 'new_value': value}


def _action_pause_qr(config: dict, context: dict, automation) -> dict:
    """Pause a QR code."""
    from apps.qrcodes.models import QRCode
    qr_id = context.get('qr_id') or (str(automation.qr_code_id) if automation.qr_code_id else None)
    if not qr_id:
        raise ValueError('No QR code ID available')
    QRCode.objects.filter(id=qr_id).update(status='paused')
    return {'qr_id': qr_id, 'status': 'paused'}


def _action_activate_qr(config: dict, context: dict, automation) -> dict:
    """Activate a QR code."""
    from apps.qrcodes.models import QRCode
    qr_id = context.get('qr_id') or (str(automation.qr_code_id) if automation.qr_code_id else None)
    if not qr_id:
        raise ValueError('No QR code ID available')
    QRCode.objects.filter(id=qr_id).update(status='active')
    return {'qr_id': qr_id, 'status': 'active'}


def _action_ai_generate_page(config: dict, context: dict, automation) -> dict:
    """Trigger AI landing page generation."""
    # Delegates to AI service
    from apps.ai_service.tasks import generate_landing_page
    prompt = config.get('prompt', '')
    qr_id = context.get('qr_id') or (str(automation.qr_code_id) if automation.qr_code_id else None)
    result = generate_landing_page.delay(qr_id=qr_id, prompt=prompt)
    return {'task_id': str(result.id)}


def _action_ai_optimize_route(config: dict, context: dict, automation) -> dict:
    """Trigger AI routing optimization."""
    from apps.ai_service.tasks import optimize_routing
    qr_id = context.get('qr_id') or (str(automation.qr_code_id) if automation.qr_code_id else None)
    result = optimize_routing.delay(qr_id=qr_id)
    return {'task_id': str(result.id)}
