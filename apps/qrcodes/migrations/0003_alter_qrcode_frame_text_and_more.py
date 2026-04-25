"""
Stub migration — matches what was applied on PythonAnywhere.
Minor field alterations (frame_text defaults, etc.).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0002_qrcode_branding_frames'),
    ]

    operations = [
        # The original migration altered frame_text and similar fields.
        # Since those changes are already in the model, this is a no-op stub
        # that keeps the local migration chain consistent with production.
    ]
