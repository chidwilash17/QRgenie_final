from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('qrcodes', '0021_productauth_productserial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentUploadForm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('title', models.CharField(blank=True, default='Upload Documents', max_length=255)),
                ('description', models.TextField(blank=True, max_length=1000)),
                ('allowed_types', models.JSONField(default=list, help_text='List of allowed category tags: photos, id_proofs, kyc, certificates, other')),
                ('allowed_extensions', models.CharField(blank=True, default='.jpg,.jpeg,.png,.pdf,.heic,.webp', help_text='Comma-separated file extensions', max_length=500)),
                ('max_file_size_mb', models.PositiveIntegerField(default=10, help_text='Per-file limit in MB')),
                ('max_files', models.PositiveIntegerField(default=5, help_text='Max files per submission')),
                ('require_name', models.BooleanField(default=True)),
                ('require_email', models.BooleanField(default=False)),
                ('require_phone', models.BooleanField(default=False)),
                ('success_message', models.CharField(blank=True, default='Documents uploaded successfully!', max_length=500)),
                ('brand_color', models.CharField(default='#6366f1', max_length=7)),
                ('notify_email', models.CharField(blank=True, help_text='Email for new-submission notifications', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('qr_code', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='doc_upload_form', to='qrcodes.qrcode')),
            ],
        ),
        migrations.CreateModel(
            name='DocumentSubmission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('submitter_name', models.CharField(blank=True, max_length=255)),
                ('submitter_email', models.EmailField(blank=True, max_length=254)),
                ('submitter_phone', models.CharField(blank=True, max_length=30)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='qrcodes.documentuploadform')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DocumentFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('original_name', models.CharField(max_length=255)),
                ('file_path', models.CharField(help_text='Relative path under MEDIA_ROOT', max_length=1024)),
                ('file_size', models.PositiveIntegerField(default=0, help_text='Bytes')),
                ('mime_type', models.CharField(blank=True, max_length=100)),
                ('category', models.CharField(blank=True, help_text='photos / id_proofs / kyc / etc.', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('submission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='files', to='qrcodes.documentsubmission')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
