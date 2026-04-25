import uuid
import apps.forms_builder.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('slug', models.CharField(default=apps.forms_builder.models._nanoid, editable=False, max_length=20, unique=True)),
                ('background_theme', models.CharField(choices=[('white', 'White'), ('gray', 'Light Gray'), ('indigo', 'Indigo'), ('purple', 'Purple'), ('teal', 'Teal'), ('rose', 'Rose'), ('amber', 'Amber'), ('sky', 'Sky Blue'), ('emerald', 'Emerald'), ('gradient_ib', 'Indigo → Blue Gradient'), ('gradient_pr', 'Purple → Rose Gradient'), ('gradient_tg', 'Teal → Green Gradient'), ('dark', 'Dark')], default='white', max_length=20)),
                ('header_color', models.CharField(default='#6366F1', help_text='Hex color for header bar', max_length=7)),
                ('header_image', models.ImageField(blank=True, null=True, upload_to='form_headers/')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='form_logos/')),
                ('is_active', models.BooleanField(default=True)),
                ('accept_responses', models.BooleanField(default=True)),
                ('requires_auth', models.BooleanField(default=False, help_text='Require login to fill form')),
                ('allow_multiple_responses', models.BooleanField(default=True)),
                ('max_responses', models.PositiveIntegerField(blank=True, null=True)),
                ('close_date', models.DateTimeField(blank=True, null=True)),
                ('confirmation_message', models.TextField(default='Thank you! Your response has been recorded.')),
                ('confirmation_redirect_url', models.URLField(blank=True)),
                ('qr_slug', models.CharField(blank=True, help_text='Slug of the QRCode that points to this form (auto-managed)', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forms', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='FormField',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('field_type', models.CharField(choices=[('short_text', 'Short Text'), ('long_text', 'Long Text / Paragraph'), ('email', 'Email Address'), ('phone', 'Phone Number'), ('number', 'Number'), ('url', 'URL / Website'), ('date', 'Date'), ('time', 'Time'), ('dropdown', 'Dropdown'), ('radio', 'Multiple Choice (Radio)'), ('checkbox', 'Checkboxes'), ('rating', 'Rating (1-5 Stars)'), ('scale', 'Linear Scale'), ('file', 'File Upload (any)'), ('image', 'Photo / Image Upload'), ('video', 'Video Upload'), ('voice', 'Voice Recording'), ('pdf', 'PDF Upload'), ('document', 'Document (DOCX / PPT / XLS)'), ('section', 'Section Header / Divider'), ('signature', 'Signature')], max_length=30)),
                ('label', models.CharField(max_length=500)),
                ('placeholder', models.CharField(blank=True, max_length=255)),
                ('help_text', models.CharField(blank=True, max_length=500)),
                ('is_required', models.BooleanField(default=False)),
                ('options', models.JSONField(blank=True, default=list, help_text='List of option strings for choice fields')),
                ('min_length', models.PositiveIntegerField(blank=True, null=True)),
                ('max_length', models.PositiveIntegerField(blank=True, null=True)),
                ('min_value', models.FloatField(blank=True, null=True)),
                ('max_value', models.FloatField(blank=True, null=True)),
                ('scale_min', models.PositiveSmallIntegerField(default=1)),
                ('scale_max', models.PositiveSmallIntegerField(default=5)),
                ('scale_min_label', models.CharField(blank=True, max_length=50)),
                ('scale_max_label', models.CharField(blank=True, max_length=50)),
                ('max_file_size_mb', models.PositiveSmallIntegerField(default=10)),
                ('allowed_file_types', models.JSONField(blank=True, default=list)),
                ('is_location_restricted', models.BooleanField(default=False)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='forms_builder.form')),
            ],
            options={'ordering': ['order']},
        ),
        migrations.CreateModel(
            name='FormFieldLocationRestriction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('city', models.CharField(blank=True, help_text='e.g. Bangalore', max_length=100)),
                ('state', models.CharField(blank=True, help_text='e.g. Karnataka', max_length=100)),
                ('country', models.CharField(blank=True, help_text='ISO code e.g. IN', max_length=5)),
                ('restriction_message', models.CharField(default='This field is only available for users in a specific location.', max_length=500)),
                ('field', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='location_restriction', to='forms_builder.formfield')),
            ],
            options={'verbose_name': 'Field Location Restriction'},
        ),
        migrations.CreateModel(
            name='FormSubmission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('country', models.CharField(blank=True, max_length=5)),
                ('session_key', models.CharField(blank=True, db_index=True, max_length=64)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='forms_builder.form')),
                ('respondent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='form_submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-submitted_at']},
        ),
        migrations.CreateModel(
            name='SubmissionAnswer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('field_label', models.CharField(blank=True, help_text='Snapshot of label at submission time', max_length=500)),
                ('field_type', models.CharField(blank=True, max_length=30)),
                ('text_value', models.TextField(blank=True)),
                ('number_value', models.FloatField(blank=True, null=True)),
                ('json_value', models.JSONField(blank=True, help_text='For checkbox / multi-select', null=True)),
                ('file_value', models.FileField(blank=True, null=True, upload_to=apps.forms_builder.models.submission_file_upload_path)),
                ('field', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answers', to='forms_builder.formfield')),
                ('submission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='forms_builder.formsubmission')),
            ],
            options={'ordering': ['submission__submitted_at']},
        ),
    ]
