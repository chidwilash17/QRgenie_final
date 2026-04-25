from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0027_qrcode_utm_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='qrcode',
            name='animation_glow',
            field=models.BooleanField(default=False, help_text='Enable glow edge animation'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='glow_color',
            field=models.CharField(default='#22D3EE', max_length=7, help_text='Glow colour hex'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='glow_intensity',
            field=models.PositiveSmallIntegerField(default=2, help_text='Glow intensity 1-5'),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='gif_background_url',
            field=models.URLField(blank=True, default='', max_length=2048, help_text='GIF background behind QR'),
        ),
    ]
