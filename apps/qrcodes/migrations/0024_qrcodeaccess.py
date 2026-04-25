import django.db.models.deletion
import uuid
from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('qrcodes', '0023_funnelconfig_funnelstep_funnelsession'),
    ]

    operations = [
        migrations.CreateModel(
            name='QRCodeAccess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(choices=[('owner', 'Owner'), ('admin', 'Admin'), ('editor', 'Editor'), ('viewer', 'Viewer')], default='viewer', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_list', to='qrcodes.qrcode')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='qr_access', to=settings.AUTH_USER_MODEL)),
                ('granted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='qr_grants', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['role', 'created_at'],
                'unique_together': {('qr_code', 'user')},
            },
        ),
    ]
