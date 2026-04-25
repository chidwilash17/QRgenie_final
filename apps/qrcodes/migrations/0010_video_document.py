"""
Migration: Create VideoDocument model (Feature 13 — Video QR)
"""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('qrcodes', '0009_pdf_document'),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('original_filename', models.CharField(help_text='Original uploaded filename', max_length=500)),
                ('file_path', models.CharField(help_text='Relative path under MEDIA_ROOT', max_length=1024)),
                ('file_size', models.BigIntegerField(default=0, help_text='Size in bytes')),
                ('mime_type', models.CharField(default='video/mp4', max_length=100)),
                ('duration_seconds', models.FloatField(default=0, help_text='Duration in seconds (0=unknown)')),
                ('access_token', models.UUIDField(db_index=True, default=uuid.uuid4, help_text='Signed token for public player URL', unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('allow_download', models.BooleanField(default=False, help_text='Show download button in player')),
                ('autoplay', models.BooleanField(default=False, help_text='Auto-play on page load')),
                ('loop', models.BooleanField(default=False, help_text='Loop video playback')),
                ('title', models.CharField(blank=True, help_text='Display title in player (defaults to filename)', max_length=500)),
                ('thumbnail_path', models.CharField(blank=True, help_text='Relative path to poster/thumbnail image', max_length=1024)),
                ('view_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='video_document', to='qrcodes.qrcode')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Video Document',
            },
        ),
    ]
