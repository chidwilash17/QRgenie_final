# Generated — Feature 20: Short-Lived Token Redirects

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0014_deeplink'),
    ]

    operations = [
        migrations.CreateModel(
            name='TokenRedirect',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('mode', models.CharField(
                    choices=[('timed', 'Time-limited'), ('single_use', 'Single Use'), ('limited_sessions', 'Limited Sessions')],
                    default='timed', max_length=20,
                )),
                ('ttl_seconds', models.IntegerField(default=60, help_text='Token lifetime in seconds (e.g. 60 = 1 minute)')),
                ('max_uses', models.IntegerField(default=1, help_text='Max redemptions per token (applies to single_use and limited_sessions)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='token_redirect',
                    to='qrcodes.qrcode',
                )),
            ],
            options={
                'verbose_name': 'Token Redirect',
            },
        ),
        migrations.CreateModel(
            name='TokenUsage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('jti', models.CharField(db_index=True, help_text='JWT ID — unique per token', max_length=64)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('session_key', models.CharField(blank=True, default='', max_length=128)),
                ('used_at', models.DateTimeField(auto_now_add=True)),
                ('token_redirect', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='usages',
                    to='qrcodes.tokenredirect',
                )),
            ],
            options={
                'ordering': ['-used_at'],
            },
        ),
    ]
