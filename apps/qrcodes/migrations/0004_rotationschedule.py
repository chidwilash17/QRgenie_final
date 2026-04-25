"""
Migration: Add RotationSchedule — auto-rotating landing pages per QR code.
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0003_alter_qrcode_frame_text_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='RotationSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('rotation_type', models.CharField(
                    choices=[
                        ('daily',  'Daily (cycles through list each day)'),
                        ('weekly', 'Weekly (one page per day-of-week)'),
                        ('custom', 'Custom (date range per page)'),
                    ],
                    default='daily',
                    max_length=20,
                )),
                ('tz', models.CharField(default='UTC', help_text='IANA timezone e.g. Asia/Kolkata', max_length=50)),
                ('pages', models.JSONField(default=list, help_text='Ordered page entries for rotation')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rotation_schedule',
                    to='qrcodes.qrcode',
                )),
            ],
            options={'verbose_name': 'Rotation Schedule'},
        ),
    ]
