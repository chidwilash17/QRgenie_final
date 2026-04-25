"""Feature 25 — Scan Alerts model."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0017_qr_expiry'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScanAlert',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('alert_events', models.JSONField(default=list, help_text='List of event types: every_scan, milestone, first_scan, scan_spike')),
                ('email_recipients', models.TextField(blank=True, help_text='Comma-separated email addresses to notify')),
                ('milestone_every', models.IntegerField(default=100, help_text='Send alert every N scans (for milestone event)')),
                ('spike_window_minutes', models.IntegerField(default=60)),
                ('spike_threshold', models.IntegerField(default=50, help_text='Alert if scans exceed this count within the window')),
                ('cooldown_minutes', models.IntegerField(default=5, help_text='Min minutes between alerts to prevent spam')),
                ('last_notified_at', models.DateTimeField(blank=True, null=True)),
                ('total_alerts_sent', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='scan_alert', to='qrcodes.qrcode')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
