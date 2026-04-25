import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0022_documentuploadform_documentsubmission_documentfile'),
    ]

    operations = [
        migrations.CreateModel(
            name='FunnelConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('brand_color', models.CharField(blank=True, default='#6366f1', max_length=20)),
                ('show_progress_bar', models.BooleanField(default=True)),
                ('allow_back_navigation', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='funnel_config', to='qrcodes.qrcode')),
            ],
        ),
        migrations.CreateModel(
            name='FunnelStep',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('step_order', models.PositiveIntegerField(default=0)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('content', models.TextField(blank=True, help_text='Body text / HTML for this step')),
                ('image_url', models.URLField(blank=True, max_length=500)),
                ('button_text', models.CharField(blank=True, default='Next', max_length=100)),
                ('button_url', models.URLField(blank=True, help_text='External link on last step (optional)', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('funnel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='qrcodes.funnelconfig')),
            ],
            options={
                'ordering': ['step_order'],
            },
        ),
        migrations.CreateModel(
            name='FunnelSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('session_key', models.CharField(help_text='Browser session / cookie ID', max_length=64)),
                ('current_step', models.PositiveIntegerField(default=0)),
                ('is_completed', models.BooleanField(default=False)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(null=True, blank=True)),
                ('funnel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='qrcodes.funnelconfig')),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
    ]
