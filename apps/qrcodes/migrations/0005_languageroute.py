"""
Migration: Add LanguageRoute — multi-language auto-detection per QR code.
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0004_rotationschedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='LanguageRoute',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('routes', models.JSONField(default=list, help_text='Ordered language→URL mappings')),
                ('default_url', models.URLField(blank=True, help_text='Fallback URL when no language matches', max_length=2048)),
                ('geo_fallback', models.JSONField(blank=True, default=dict, help_text='Country code→language fallback map')),
                ('use_quality_weights', models.BooleanField(default=True, help_text='Use q= weights from Accept-Language header')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='language_route',
                    to='qrcodes.qrcode',
                )),
            ],
            options={
                'verbose_name': 'Language Route',
            },
        ),
    ]
