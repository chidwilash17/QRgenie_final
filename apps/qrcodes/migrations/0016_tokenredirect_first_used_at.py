from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0015_tokenredirect_tokenusage'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokenredirect',
            name='first_used_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Set on first scan — used for timed-mode QR-level expiry',
            ),
        ),
    ]
