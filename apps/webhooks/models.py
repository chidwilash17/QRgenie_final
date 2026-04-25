"""
Webhooks — Models
===================
Webhook endpoint registration, delivery logging, and retry management.
"""
import uuid
import secrets
from django.db import models
from django.conf import settings


class WebhookEndpoint(models.Model):
    """Registered webhook URL that receives event notifications."""
    EVENT_CHOICES = [
        ('scan.created', 'Scan Created'),
        ('qr.created', 'QR Code Created'),
        ('qr.updated', 'QR Code Updated'),
        ('qr.deleted', 'QR Code Deleted'),
        ('qr.expired', 'QR Code Expired'),
        ('qr.scan_limit', 'QR Scan Limit Reached'),
        ('automation.run', 'Automation Executed'),
        ('landing_page.created', 'Landing Page Created'),
        ('bulk_upload.completed', 'Bulk Upload Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='webhook_endpoints'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )

    url = models.URLField(max_length=2048)
    description = models.CharField(max_length=500, blank=True, default='')
    secret = models.CharField(max_length=128, help_text='HMAC signing secret')
    events = models.JSONField(default=list, help_text='List of event types to subscribe to')
    is_active = models.BooleanField(default=True)

    # Headers to include
    custom_headers = models.JSONField(default=dict, blank=True)

    # Failure tracking
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    disabled_reason = models.CharField(max_length=500, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.url} ({len(self.events)} events)"

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    # Auto-disable after 10 consecutive failures
    MAX_CONSECUTIVE_FAILURES = 10


class WebhookDelivery(models.Model):
    """Log of each webhook delivery attempt."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Request
    payload = models.JSONField(default=dict)
    request_headers = models.JSONField(default=dict)

    # Response
    response_status_code = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default='')
    response_headers = models.JSONField(default=dict, blank=True)

    # Retry
    attempt = models.PositiveSmallIntegerField(default=1)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True, default='')
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-delivered_at']
        indexes = [
            models.Index(fields=['endpoint', '-delivered_at']),
            models.Index(fields=['status', 'next_retry_at']),
        ]

    def __str__(self):
        return f"{self.event_type} → {self.endpoint.url} ({self.status})"
