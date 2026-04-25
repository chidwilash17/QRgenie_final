from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0028_qrcode_animated_qr'),
    ]

    operations = [
        # Soft delete field
        migrations.AddField(
            model_name='qrcode',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        # Composite index: status + organization — covers "show active QRs for this org" queries
        migrations.AddIndex(
            model_name='qrcode',
            index=models.Index(fields=['status', 'organization'], name='qrcode_status_org_idx'),
        ),
    ]
