"""
Feature 28 — Digital vCard QR
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0019_loyalty_program'),
    ]

    operations = [
        migrations.CreateModel(
            name='DigitalVCard',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(blank=True, max_length=100)),
                ('prefix', models.CharField(blank=True, help_text='e.g. Dr., Mr., Mrs.', max_length=20)),
                ('suffix', models.CharField(blank=True, help_text='e.g. Jr., PhD', max_length=20)),
                ('organization', models.CharField(blank=True, max_length=200)),
                ('title', models.CharField(blank=True, help_text='Job title', max_length=200)),
                ('department', models.CharField(blank=True, max_length=200)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('email_work', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('phone_work', models.CharField(blank=True, max_length=30)),
                ('phone_cell', models.CharField(blank=True, max_length=30)),
                ('website', models.URLField(blank=True)),
                ('linkedin', models.URLField(blank=True)),
                ('twitter', models.CharField(blank=True, max_length=100)),
                ('github', models.URLField(blank=True)),
                ('instagram', models.CharField(blank=True, max_length=100)),
                ('street', models.CharField(blank=True, max_length=300)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('zip_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('photo_url', models.URLField(blank=True, help_text='Profile photo URL')),
                ('accent_color', models.CharField(default='#6366f1', help_text='Hex color for card accent', max_length=7)),
                ('bio', models.TextField(blank=True, max_length=500)),
                ('note', models.TextField(blank=True, max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vcard', to='qrcodes.qrcode')),
            ],
            options={
                'verbose_name': 'Digital vCard',
                'verbose_name_plural': 'Digital vCards',
            },
        ),
    ]
