"""
Migration for Feature 15: Device-Based Redirect (DeviceRoute model).
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0010_video_document'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceRoute',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('android_url', models.URLField(blank=True, default='', help_text='Redirect URL for Android devices', max_length=2048)),
                ('ios_url', models.URLField(blank=True, default='', help_text='Redirect URL for iOS devices (iPhone/iPad)', max_length=2048)),
                ('windows_url', models.URLField(blank=True, default='', help_text='Redirect URL for Windows devices', max_length=2048)),
                ('mac_url', models.URLField(blank=True, default='', help_text='Redirect URL for macOS devices', max_length=2048)),
                ('linux_url', models.URLField(blank=True, default='', help_text='Redirect URL for Linux devices', max_length=2048)),
                ('tablet_url', models.URLField(blank=True, default='', help_text='Redirect URL specifically for tablets (iPad, Android tablet)', max_length=2048)),
                ('default_url', models.URLField(blank=True, default='', help_text='Fallback URL when no device rule matches', max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='device_route', to='qrcodes.qrcode')),
            ],
            options={
                'verbose_name': 'Device Route',
            },
        ),
    ]
