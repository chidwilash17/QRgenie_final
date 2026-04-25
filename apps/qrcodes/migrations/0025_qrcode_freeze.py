"""Feature 38 — Freeze Mode: add is_frozen, frozen_by, frozen_at to QRCode."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('qrcodes', '0024_qrcodeaccess'),
    ]

    operations = [
        migrations.AddField(
            model_name='qrcode',
            name='is_frozen',
            field=models.BooleanField(default=False, help_text='Locked — only owner/admin can edit'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='frozen_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='frozen_qr_codes',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='frozen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
