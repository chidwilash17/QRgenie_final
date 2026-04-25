"""
Migration: Create ABTest model (Feature 18 — A/B Split Testing)
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0012_geofence_rule'),
    ]

    operations = [
        migrations.CreateModel(
            name='ABTest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('variants', models.JSONField(default=list, help_text='Ordered list of variants [{label, url, weight}]')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='ab_test', to='qrcodes.qrcode')),
            ],
            options={
                'verbose_name': 'A/B Split Test',
            },
        ),
    ]
