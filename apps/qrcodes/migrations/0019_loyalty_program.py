"""Feature 26 — Loyalty Point QR models."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0018_scan_alert'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoyaltyProgram',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('program_name', models.CharField(default='Loyalty Rewards', max_length=200)),
                ('points_per_scan', models.IntegerField(default=1, help_text='Points awarded per scan')),
                ('max_points_per_day', models.IntegerField(default=10, help_text='Max points a single member can earn per day (0 = unlimited)')),
                ('bonus_points', models.IntegerField(default=0, help_text='Extra bonus points on first scan')),
                ('reward_tiers', models.JSONField(default=list, help_text='List of reward tiers: [{name, points_required, description}]')),
                ('total_members', models.IntegerField(default=0)),
                ('total_points_issued', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_program', to='qrcodes.qrcode')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LoyaltyMember',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('identifier', models.CharField(help_text='Email or phone number', max_length=255)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('points', models.IntegerField(default=0)),
                ('total_scans', models.IntegerField(default=0)),
                ('last_scan_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='qrcodes.loyaltyprogram')),
            ],
            options={
                'ordering': ['-points'],
                'unique_together': {('program', 'identifier')},
            },
        ),
    ]
