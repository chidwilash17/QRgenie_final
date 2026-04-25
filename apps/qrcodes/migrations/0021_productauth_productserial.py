"""
Feature 31 — Product Authentication QR
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0020_digitalvcard'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductAuth',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('product_name', models.CharField(max_length=255)),
                ('manufacturer', models.CharField(blank=True, max_length=255)),
                ('description', models.TextField(blank=True, max_length=1000)),
                ('product_image_url', models.URLField(blank=True)),
                ('secret_key', models.CharField(help_text='HMAC secret for signing serials', max_length=128)),
                ('brand_color', models.CharField(default='#22c55e', max_length=7)),
                ('support_url', models.URLField(blank=True)),
                ('support_email', models.EmailField(blank=True, max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='product_auth', to='qrcodes.qrcode')),
            ],
        ),
        migrations.CreateModel(
            name='ProductSerial',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('serial_number', models.CharField(db_index=True, max_length=64)),
                ('hmac_signature', models.CharField(max_length=128)),
                ('status', models.CharField(choices=[('unscanned', 'Unscanned'), ('verified', 'Verified'), ('flagged', 'Flagged')], default='unscanned', max_length=20)),
                ('batch_label', models.CharField(blank=True, max_length=100)),
                ('manufactured_date', models.DateField(blank=True, null=True)),
                ('total_scans', models.PositiveIntegerField(default=0)),
                ('first_scanned_at', models.DateTimeField(blank=True, null=True)),
                ('last_scanned_at', models.DateTimeField(blank=True, null=True)),
                ('last_scanned_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('last_scanned_location', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product_auth', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='serials', to='qrcodes.productauth')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('product_auth', 'serial_number')},
            },
        ),
    ]
