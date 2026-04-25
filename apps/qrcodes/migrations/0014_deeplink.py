"""
Migration: Create DeepLink model (Feature 19 — App Deep Linking)
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0013_abtest'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeepLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('ios_deep_link', models.URLField(blank=True, default='', help_text='iOS Universal Link or custom URI scheme', max_length=2048)),
                ('ios_fallback_url', models.URLField(blank=True, default='', help_text='Fallback URL if app not installed (App Store)', max_length=2048)),
                ('android_deep_link', models.URLField(blank=True, default='', help_text='Android App Link or custom URI scheme', max_length=2048)),
                ('android_fallback_url', models.URLField(blank=True, default='', help_text='Fallback URL if app not installed (Play Store)', max_length=2048)),
                ('custom_uri', models.CharField(blank=True, default='', help_text='Custom URI scheme e.g. myapp://path', max_length=2048)),
                ('fallback_url', models.URLField(blank=True, default='', help_text='Fallback for desktop or other', max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='deep_link', to='qrcodes.qrcode')),
            ],
            options={
                'verbose_name': 'App Deep Link',
            },
        ),
    ]
