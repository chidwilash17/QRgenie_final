"""
Automation Engine — Models
============================
Event-driven automations: triggers → conditions → actions
Scheduled behaviors, hooks, and external integrations.
"""
import uuid
from django.db import models
from django.conf import settings


class Automation(models.Model):
    """
    Top-level automation workflow.
    An automation has one trigger and one or more actions.
    """
    TRIGGER_TYPE_CHOICES = [
        ('scan_created', 'QR Code Scanned'),
        ('scan_from_country', 'Scan From Country'),
        ('scan_device_type', 'Scan From Device Type'),
        ('scan_limit_reached', 'Scan Limit Reached'),
        ('qr_expired', 'QR Code Expired'),
        ('qr_created', 'QR Code Created'),
        ('bulk_upload_completed', 'Bulk Upload Completed'),
        ('schedule', 'Scheduled (Cron)'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('draft', 'Draft'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='automations'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='automations'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    trigger_type = models.CharField(max_length=50, choices=TRIGGER_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Optional: link to specific QR code(s)
    qr_code = models.ForeignKey(
        'qrcodes.QRCode', on_delete=models.CASCADE, null=True, blank=True,
        related_name='automations', help_text='If set, trigger only fires for this QR.'
    )

    # For schedule trigger
    cron_expression = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Cron expression for schedule trigger (e.g. "0 9 * * 1" for Mon 9AM)'
    )

    total_runs = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['trigger_type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.trigger_type})"


class AutomationCondition(models.Model):
    """
    Optional filter conditions that must all pass for the automation to run.
    E.g., "country == IN", "device_type == mobile"
    """
    OPERATOR_CHOICES = [
        ('eq', 'Equals'),
        ('neq', 'Not Equals'),
        ('contains', 'Contains'),
        ('gt', 'Greater Than'),
        ('lt', 'Less Than'),
        ('gte', 'Greater or Equal'),
        ('lte', 'Less or Equal'),
        ('in', 'In List'),
        ('not_in', 'Not In List'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name='conditions')
    field = models.CharField(max_length=100, help_text='e.g. country, device_type, os, browser, scan_count')
    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES)
    value = models.CharField(max_length=500, blank=True, default='')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.field} {self.operator} {self.value}"

    def evaluate(self, context: dict) -> bool:
        """Evaluate this condition against scan/event context."""
        actual = context.get(self.field, '')
        expected = self.value

        if self.operator == 'eq':
            return str(actual).lower() == expected.lower()
        elif self.operator == 'neq':
            return str(actual).lower() != expected.lower()
        elif self.operator == 'contains':
            return expected.lower() in str(actual).lower()
        elif self.operator == 'gt':
            try:
                return float(actual) > float(expected)
            except ValueError:
                return False
        elif self.operator == 'lt':
            try:
                return float(actual) < float(expected)
            except ValueError:
                return False
        elif self.operator == 'gte':
            try:
                return float(actual) >= float(expected)
            except ValueError:
                return False
        elif self.operator == 'lte':
            try:
                return float(actual) <= float(expected)
            except ValueError:
                return False
        elif self.operator == 'in':
            values = [v.strip().lower() for v in expected.split(',')]
            return str(actual).lower() in values
        elif self.operator == 'not_in':
            values = [v.strip().lower() for v in expected.split(',')]
            return str(actual).lower() not in values
        return False


class AutomationAction(models.Model):
    """
    Action to execute when automation fires.
    """
    ACTION_TYPE_CHOICES = [
        ('send_email', 'Send Email'),
        ('send_sms', 'Send SMS'),
        ('send_whatsapp', 'Send WhatsApp Message'),
        ('send_slack', 'Send Slack Notification'),
        ('send_teams', 'Send MS Teams Notification'),
        ('webhook', 'Call Webhook URL'),
        ('update_qr', 'Update QR Code'),
        ('pause_qr', 'Pause QR Code'),
        ('activate_qr', 'Activate QR Code'),
        ('ai_generate_page', 'AI Generate Landing Page'),
        ('ai_optimize_route', 'AI Optimize Routing'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES)
    order = models.PositiveSmallIntegerField(default=0)

    # Flexible payload for different action types
    config = models.JSONField(default=dict, help_text=(
        'Action config. Examples:\n'
        'send_email: {"to": "a@b.com", "subject": "...", "template": "scan_alert"}\n'
        'webhook: {"url": "https://...", "method": "POST", "headers": {...}}\n'
        'send_slack: {"webhook_url": "https://hooks.slack.com/...", "message": "..."}\n'
        'update_qr: {"field": "destination_url", "value": "https://new-url.com"}\n'
        'ai_generate_page: {"prompt": "Create a product page for..."}'
    ))

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.action_type} (order {self.order})"


class AutomationRun(models.Model):
    """
    Record of each automation execution.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped — Conditions Not Met'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger_data = models.JSONField(default=dict, help_text='Trigger event payload')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['automation', '-started_at']),
        ]

    def __str__(self):
        return f"Run {self.id} — {self.status}"


class AutomationActionLog(models.Model):
    """
    Log of each action execution within a run.
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AutomationRun, on_delete=models.CASCADE, related_name='action_logs')
    action = models.ForeignKey(AutomationAction, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    input_data = models.JSONField(default=dict)
    output_data = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')
    executed_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['executed_at']

    def __str__(self):
        return f"Action {self.action} — {self.status}"


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduled QR Behavior — activate/deactivate/change redirect on a schedule
# ═══════════════════════════════════════════════════════════════════════════════

class QRSchedule(models.Model):
    """
    Schedule future behavior changes on a QR code.
    E.g. "Activate this QR at 9 AM Mon, pause at 5 PM Fri", or
    "Switch destination to promo URL on Black Friday".
    """
    ACTION_CHOICES = [
        ('activate', 'Activate QR'),
        ('pause', 'Pause QR'),
        ('expire', 'Expire QR'),
        ('change_url', 'Change Destination URL'),
        ('change_fallback', 'Change Fallback URL'),
        ('rotate_page', 'Rotate to Next Page'),
    ]

    REPEAT_CHOICES = [
        ('once', 'One-time'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('cron', 'Cron Expression'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='qr_schedules'
    )
    qr_code = models.ForeignKey(
        'qrcodes.QRCode', on_delete=models.CASCADE, related_name='schedules'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )

    name = models.CharField(max_length=255)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    is_active = models.BooleanField(default=True)

    # When to execute
    scheduled_at = models.DateTimeField(
        null=True, blank=True,
        help_text='For one-time schedules: exact datetime to execute'
    )
    repeat = models.CharField(max_length=20, choices=REPEAT_CHOICES, default='once')
    cron_expression = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Cron expression for recurring schedules (e.g. "0 9 * * 1-5")'
    )
    tz = models.CharField(max_length=50, default='UTC', help_text='IANA timezone')

    # Action payload
    payload = models.JSONField(default=dict, blank=True, help_text=(
        'Action-specific config. Examples:\n'
        'change_url: {"url": "https://new-destination.com"}\n'
        'change_fallback: {"url": "https://fallback.com"}'
    ))

    # Execution tracking
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    total_runs = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run_at']
        indexes = [
            models.Index(fields=['is_active', 'next_run_at']),
            models.Index(fields=['qr_code', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name} — {self.action} ({self.repeat})"


class QRScheduleLog(models.Model):
    """Execution log for each scheduled action run."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(QRSchedule, on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=20, choices=[
        ('success', 'Success'), ('failed', 'Failed'),
    ])
    executed_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-executed_at']


# ═══════════════════════════════════════════════════════════════════════════════
# n8n / Zapier Integration — External automation platform subscriptions
# ═══════════════════════════════════════════════════════════════════════════════

class ExternalHookSubscription(models.Model):
    """
    Webhook subscription from n8n, Zapier, Make, or any external automation platform.
    They POST a target_url when subscribing, we fire events to that URL.
    Implements the REST Hooks pattern (https://resthooks.org).
    """
    EVENT_CHOICES = [
        ('scan.created', 'QR Code Scanned'),
        ('qr.created', 'QR Code Created'),
        ('qr.updated', 'QR Code Updated'),
        ('qr.expired', 'QR Code Expired'),
        ('qr.scan_limit', 'Scan Limit Reached'),
        ('automation.run', 'Automation Executed'),
        ('schedule.executed', 'Schedule Executed'),
        ('conversion.created', 'Conversion Event'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='hook_subscriptions'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )

    event = models.CharField(max_length=50, choices=EVENT_CHOICES)
    target_url = models.URLField(max_length=2048)
    is_active = models.BooleanField(default=True)

    # Platform identification
    platform = models.CharField(max_length=50, blank=True, default='',
                                help_text='e.g. zapier, n8n, make, custom')

    # Failure tracking
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'event', 'is_active']),
        ]

    def __str__(self):
        return f"{self.platform or 'hook'}: {self.event} → {self.target_url}"
