"""
Migration: Add branding, styling, frame, and static QR fields to QRCode.

New fields:
  - is_dynamic, static_content (static vs dynamic QR support)
  - module_style (square/rounded/circle/gapped/bars)
  - gradient_type, gradient_start_color, gradient_end_color
  - frame_style, frame_color, frame_text, frame_text_color
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0001_initial'),
    ]

    operations = [
        # ── Static vs Dynamic ────────────────────────
        migrations.AddField(
            model_name='qrcode',
            name='is_dynamic',
            field=models.BooleanField(
                default=True,
                help_text='Dynamic QR encodes redirect URL; static encodes raw content',
            ),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='static_content',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Raw content for static QR (URL, text, vCard, WiFi, etc.)',
            ),
        ),

        # ── Module Style ─────────────────────────────
        migrations.AddField(
            model_name='qrcode',
            name='module_style',
            field=models.CharField(
                max_length=20,
                default='square',
                choices=[
                    ('square', 'Square'),
                    ('rounded', 'Rounded'),
                    ('circle', 'Circle'),
                    ('gapped', 'Gapped Square'),
                    ('vertical_bars', 'Vertical Bars'),
                    ('horizontal_bars', 'Horizontal Bars'),
                ],
            ),
        ),

        # ── Gradient ─────────────────────────────────
        migrations.AddField(
            model_name='qrcode',
            name='gradient_type',
            field=models.CharField(
                max_length=20,
                default='none',
                choices=[
                    ('none', 'No Gradient'),
                    ('linear_h', 'Horizontal'),
                    ('linear_v', 'Vertical'),
                    ('radial', 'Radial'),
                    ('square', 'Square'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='gradient_start_color',
            field=models.CharField(max_length=7, blank=True, default='', help_text='Gradient start colour'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='gradient_end_color',
            field=models.CharField(max_length=7, blank=True, default='', help_text='Gradient end colour'),
        ),

        # ── Frame / CTA ─────────────────────────────
        migrations.AddField(
            model_name='qrcode',
            name='frame_style',
            field=models.CharField(
                max_length=30,
                default='none',
                choices=[
                    ('none', 'No Frame'),
                    ('banner_bottom', 'Banner Bottom'),
                    ('banner_top', 'Banner Top'),
                    ('rounded_box', 'Rounded Box'),
                    ('ticket', 'Ticket'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='frame_color',
            field=models.CharField(max_length=7, default='#000000'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='frame_text',
            field=models.CharField(max_length=100, blank=True, default='', help_text='CTA text e.g. "Scan Me"'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='frame_text_color',
            field=models.CharField(max_length=7, default='#FFFFFF'),
        ),
    ]
