from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0026_bulk_upload_file_url_to_charfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='qrcode',
            name='utm_source',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='utm_medium',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='qrcode',
            name='utm_campaign',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
