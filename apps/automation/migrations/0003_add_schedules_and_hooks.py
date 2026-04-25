# Generated migration for QRSchedule, QRScheduleLog, ExternalHookSubscription

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0002_initial"),
        ("core", "0001_initial"),
        ("qrcodes", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── QRSchedule ──────────────────────────────────────────────
        migrations.CreateModel(
            name="QRSchedule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("action", models.CharField(
                    choices=[
                        ("activate", "Activate QR"),
                        ("pause", "Pause QR"),
                        ("expire", "Expire QR"),
                        ("change_url", "Change Destination URL"),
                        ("change_fallback", "Change Fallback URL"),
                        ("rotate_page", "Rotate to Next Page"),
                    ],
                    max_length=30,
                )),
                ("is_active", models.BooleanField(default=True)),
                ("scheduled_at", models.DateTimeField(blank=True, help_text="For one-time schedules: exact datetime to execute", null=True)),
                ("repeat", models.CharField(
                    choices=[
                        ("once", "One-time"),
                        ("daily", "Daily"),
                        ("weekly", "Weekly"),
                        ("monthly", "Monthly"),
                        ("cron", "Cron Expression"),
                    ],
                    default="once",
                    max_length=20,
                )),
                ("cron_expression", models.CharField(blank=True, default="", help_text='Cron expression for recurring schedules (e.g. "0 9 * * 1-5")', max_length=100)),
                ("tz", models.CharField(default="UTC", help_text="IANA timezone", max_length=50)),
                ("payload", models.JSONField(blank=True, default=dict, help_text='Action-specific config. Examples:\nchange_url: {"url": "https://new-destination.com"}\nchange_fallback: {"url": "https://fallback.com"}')),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("next_run_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("total_runs", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="qr_schedules", to="core.organization")),
                ("qr_code", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="schedules", to="qrcodes.qrcode")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["next_run_at"],
            },
        ),
        migrations.AddIndex(
            model_name="qrschedule",
            index=models.Index(fields=["is_active", "next_run_at"], name="automation__is_acti_sched_idx"),
        ),
        migrations.AddIndex(
            model_name="qrschedule",
            index=models.Index(fields=["qr_code", "-created_at"], name="automation__qr_cod_sched_idx"),
        ),

        # ── QRScheduleLog ───────────────────────────────────────────
        migrations.CreateModel(
            name="QRScheduleLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], max_length=20)),
                ("executed_at", models.DateTimeField(auto_now_add=True)),
                ("details", models.JSONField(default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                ("schedule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="automation.qrschedule")),
            ],
            options={
                "ordering": ["-executed_at"],
            },
        ),

        # ── ExternalHookSubscription ────────────────────────────────
        migrations.CreateModel(
            name="ExternalHookSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event", models.CharField(
                    choices=[
                        ("scan.created", "QR Code Scanned"),
                        ("qr.created", "QR Code Created"),
                        ("qr.updated", "QR Code Updated"),
                        ("qr.expired", "QR Code Expired"),
                        ("qr.scan_limit", "Scan Limit Reached"),
                        ("automation.run", "Automation Executed"),
                        ("schedule.executed", "Schedule Executed"),
                        ("conversion.created", "Conversion Event"),
                    ],
                    max_length=50,
                )),
                ("target_url", models.URLField(max_length=2048)),
                ("is_active", models.BooleanField(default=True)),
                ("platform", models.CharField(blank=True, default="", help_text="e.g. zapier, n8n, make, custom", max_length=50)),
                ("consecutive_failures", models.PositiveIntegerField(default=0)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hook_subscriptions", to="core.organization")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="externalhooksubscription",
            index=models.Index(fields=["organization", "event", "is_active"], name="automation__org_evt_hook_idx"),
        ),
    ]
