"""
Webhooks — Celery Tasks
=========================
Deliver webhook payloads with retry and exponential backoff.
"""
import hmac
import json
import time
import hashlib
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('qrgenie')


@shared_task(queue='default', ignore_result=True)
def dispatch_webhook_event(event_type: str, payload: dict, org_id: str):
    """
    Find all active endpoints subscribed to this event and send payloads.
    """
    from apps.webhooks.models import WebhookEndpoint

    endpoints = WebhookEndpoint.objects.filter(
        organization_id=org_id,
        is_active=True,
    )

    for ep in endpoints:
        if event_type in ep.events or '*' in ep.events:
            deliver_webhook.delay(str(ep.id), event_type, payload)


@shared_task(queue='default', bind=True, max_retries=5)
def deliver_webhook(self, endpoint_id: str, event_type: str, payload: dict, attempt: int = 1):
    """
    Deliver a single webhook payload with HMAC signing and retry.
    """
    import httpx
    from apps.webhooks.models import WebhookEndpoint, WebhookDelivery

    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id, is_active=True)
    except WebhookEndpoint.DoesNotExist:
        return

    body = json.dumps(payload, default=str)

    # Sign with HMAC-SHA256
    signature = hmac.new(
        endpoint.secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        'Content-Type': 'application/json',
        'X-QRGenie-Event': event_type,
        'X-QRGenie-Signature': f'sha256={signature}',
        'X-QRGenie-Delivery': str(endpoint_id),
        'X-QRGenie-Timestamp': str(int(timezone.now().timestamp())),
        **endpoint.custom_headers,
    }

    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        status='pending',
        payload=payload,
        request_headers={k: v for k, v in headers.items() if 'secret' not in k.lower()},
        attempt=attempt,
    )

    start = time.time()
    try:
        response = httpx.post(
            endpoint.url,
            content=body,
            headers=headers,
            timeout=15,
        )
        duration = int((time.time() - start) * 1000)

        delivery.response_status_code = response.status_code
        delivery.response_body = response.text[:2000]
        delivery.duration_ms = duration

        if 200 <= response.status_code < 300:
            delivery.status = 'success'
            delivery.save()
            # Reset failure counter on success
            endpoint.consecutive_failures = 0
            endpoint.save(update_fields=['consecutive_failures'])
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text[:300]}")

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        delivery.status = 'failed'
        delivery.error_message = str(e)
        delivery.duration_ms = duration

        # Track failures
        endpoint.consecutive_failures += 1
        endpoint.last_failure_at = timezone.now()

        if endpoint.consecutive_failures >= WebhookEndpoint.MAX_CONSECUTIVE_FAILURES:
            endpoint.is_active = False
            endpoint.disabled_reason = f'Auto-disabled after {endpoint.consecutive_failures} consecutive failures'
            logger.warning(f"Webhook endpoint {endpoint.id} auto-disabled after {endpoint.consecutive_failures} failures")

        endpoint.save(update_fields=['consecutive_failures', 'last_failure_at', 'is_active', 'disabled_reason'])

        # Retry with exponential backoff
        if attempt < 5:
            backoff = 2 ** attempt * 30  # 60s, 120s, 240s, 480s
            delivery.status = 'retrying'
            delivery.next_retry_at = timezone.now() + timedelta(seconds=backoff)
            delivery.save()
            raise self.retry(
                exc=e,
                countdown=backoff,
                kwargs={'endpoint_id': endpoint_id, 'event_type': event_type, 'payload': payload, 'attempt': attempt + 1},
            )
        else:
            delivery.save()
            logger.error(f"Webhook delivery exhausted retries: {endpoint.url} / {event_type}")
