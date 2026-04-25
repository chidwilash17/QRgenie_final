"""
Analytics Models — Scan events + aggregated metrics
=====================================================
"""
import uuid
from django.db import models
from apps.qrcodes.models import QRCode


class ScanEvent(models.Model):
    """Individual QR scan event — raw event log."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='scan_events')
    # Scan details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=5, blank=True, db_index=True)
    city = models.CharField(max_length=100, blank=True)
    device_type = models.CharField(max_length=20, blank=True, db_index=True)
    os = models.CharField(max_length=30, blank=True)
    browser = models.CharField(max_length=30, blank=True)
    language = models.CharField(max_length=10, blank=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(max_length=2048, blank=True)
    # GPS (optional)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    # Routing result
    destination_url = models.URLField(max_length=2048, blank=True)
    rule_matched = models.CharField(max_length=100, blank=True, help_text='ID of the rule that matched')
    # Fingerprint for unique detection
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    is_unique = models.BooleanField(default=False)
    # Tags
    tags = models.JSONField(default=list, blank=True)
    # Timestamp
    scanned_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-scanned_at']
        indexes = [
            models.Index(fields=['qr_code', '-scanned_at']),
            models.Index(fields=['country', '-scanned_at']),
            models.Index(fields=['device_type', '-scanned_at']),
        ]

    def __str__(self):
        return f"Scan {self.qr_code.slug} from {self.country} at {self.scanned_at}"


class DailyMetric(models.Model):
    """Pre-aggregated daily metrics per QR code."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField(db_index=True)
    total_scans = models.IntegerField(default=0)
    unique_scans = models.IntegerField(default=0)
    # Breakdown
    country_breakdown = models.JSONField(default=dict)
    device_breakdown = models.JSONField(default=dict)
    browser_breakdown = models.JSONField(default=dict)
    os_breakdown = models.JSONField(default=dict)
    hourly_breakdown = models.JSONField(default=dict, help_text='Hour → count mapping')
    referrer_breakdown = models.JSONField(default=dict)
    # Top links clicked (for multi-link QRs)
    link_clicks = models.JSONField(default=dict)

    class Meta:
        unique_together = ['qr_code', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.qr_code.slug} — {self.date}: {self.total_scans} scans"


class LinkClickEvent(models.Model):
    """Track clicks on individual links within multi-link or landing pages."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='link_clicks')
    link_url = models.URLField(max_length=2048)
    link_label = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=5, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-clicked_at']


class ConversionEvent(models.Model):
    """
    Track conversion events triggered after a QR scan.
    Examples: form_submit, purchase, signup, page_view, button_click, download.
    Recorded from landing pages, forms, or external webhooks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='conversion_events')
    event_type = models.CharField(max_length=50, db_index=True, help_text='e.g. form_submit, purchase, signup, page_view, download')
    event_label = models.CharField(max_length=255, blank=True, help_text='Human-readable label')
    event_value = models.FloatField(default=0, help_text='Monetary value or numeric score')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=5, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=64, blank=True, db_index=True, help_text='Links conversion to a scan session')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['qr_code', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.event_label or self.qr_code.slug} at {self.created_at}"
