from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_auditlog_before_after'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='totp_secret',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='is_2fa_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='email_otp_code',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='user',
            name='email_otp_expires',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
