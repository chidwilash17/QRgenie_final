"""
Feature 17 — GPS-Radius Geo-Fence Rules
"""

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0011_device_route'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeoFenceRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('zones', models.JSONField(default=list, help_text='Ordered list of geo-fence zones [{label, lat, lng, radius_meters, url}]')),
                ('default_url', models.URLField(blank=True, default='', help_text='Fallback URL when user is outside all zones', max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='geo_fence',
                    to='qrcodes.qrcode',
                )),
            ],
            options={
                'verbose_name': 'Geo-Fence Rule',
            },
        ),
    ]
