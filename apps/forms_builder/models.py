"""
Forms Builder Models
=====================
Comprehensive form builder with location-based field restrictions,
file uploads, and QR code integration.
"""
import uuid
import os
from django.db import models
from django.conf import settings
from nanoid import generate


def _nanoid():
    return generate('abcdefghijklmnopqrstuvwxyz0123456789', 10)


def submission_file_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f"form_uploads/{instance.submission.form_id}/{instance.field_id}/{uuid.uuid4()}{ext}"


# ──────────────────────────────────────────────────────────────────────────────
# Form (the template)
# ──────────────────────────────────────────────────────────────────────────────

BACKGROUND_THEMES = [
    ('white',       'White'),
    ('gray',        'Light Gray'),
    ('indigo',      'Indigo'),
    ('purple',      'Purple'),
    ('teal',        'Teal'),
    ('rose',        'Rose'),
    ('amber',       'Amber'),
    ('sky',         'Sky Blue'),
    ('emerald',     'Emerald'),
    ('gradient_ib', 'Indigo → Blue Gradient'),
    ('gradient_pr', 'Purple → Rose Gradient'),
    ('gradient_tg', 'Teal → Green Gradient'),
    ('dark',        'Dark'),
]


class Form(models.Model):
    """A form definition created by an admin."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='forms',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    slug = models.CharField(max_length=20, unique=True, default=_nanoid, editable=False)

    # Appearance
    background_theme = models.CharField(max_length=20, default='white', choices=BACKGROUND_THEMES)
    header_color = models.CharField(max_length=7, default='#6366F1', help_text='Hex color for header bar')
    header_image = models.ImageField(upload_to='form_headers/', null=True, blank=True)
    logo = models.ImageField(upload_to='form_logos/', null=True, blank=True)

    # Behaviour
    is_active = models.BooleanField(default=True)
    accept_responses = models.BooleanField(default=True)
    requires_auth = models.BooleanField(default=False, help_text='Require login to fill form')
    requires_respondent_info = models.BooleanField(
        default=False,
        help_text='Collect respondent name + email before showing the form (like Google Forms)',
    )
    limit_one_response_per_respondent = models.BooleanField(
        default=False,
        help_text='Only allow one submission per email address',
    )
    allow_multiple_responses = models.BooleanField(default=True)
    max_responses = models.PositiveIntegerField(null=True, blank=True)
    close_date = models.DateTimeField(null=True, blank=True)

    # Confirmation
    confirmation_message = models.TextField(
        default='Thank you! Your response has been recorded.',
    )
    confirmation_redirect_url = models.URLField(blank=True)

    # QR code link (optional — can generate QR that points to this form)
    qr_slug = models.CharField(
        max_length=20, blank=True,
        help_text='Slug of the QRCode that points to this form (auto-managed)',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def public_url(self):
        return f"/f/{self.slug}/"

    @property
    def total_submissions(self):
        return self.submissions.count()


# ──────────────────────────────────────────────────────────────────────────────
# Form Fields
# ──────────────────────────────────────────────────────────────────────────────

FIELD_TYPES = [
    # Text inputs
    ('short_text',   'Short Text'),
    ('long_text',    'Long Text / Paragraph'),
    ('email',        'Email Address'),
    ('phone',        'Phone Number'),
    ('number',       'Number'),
    ('url',          'URL / Website'),
    ('date',         'Date'),
    ('time',         'Time'),
    # Choice
    ('dropdown',     'Dropdown'),
    ('radio',        'Multiple Choice (Radio)'),
    ('checkbox',     'Checkboxes'),
    ('rating',       'Rating (1-5 Stars)'),
    ('scale',        'Linear Scale'),
    # Media / File uploads
    ('file',         'File Upload (any)'),
    ('image',        'Photo / Image Upload'),
    ('video',        'Video Upload'),
    ('voice',        'Voice Recording'),
    ('pdf',          'PDF Upload'),
    ('document',     'Document (DOCX / PPT / XLS)'),
    # Special
    ('section',      'Section Header / Divider'),
    ('signature',    'Signature'),
]

ALLOWED_FILE_TYPES = {
    'file':     [],   # all
    'image':    ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    'video':    ['video/mp4', 'video/webm', 'video/ogg', 'video/quicktime'],
    'voice':    ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/webm', 'audio/mp4'],
    'pdf':      ['application/pdf'],
    'document': [
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ],
}


class FormField(models.Model):
    """A single field within a form."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='fields')
    order = models.PositiveSmallIntegerField(default=0)
    field_type = models.CharField(max_length=30, choices=FIELD_TYPES)
    label = models.CharField(max_length=500)
    placeholder = models.CharField(max_length=255, blank=True)
    help_text = models.CharField(max_length=500, blank=True)
    is_required = models.BooleanField(default=False)

    # Choices (for dropdown, radio, checkbox)
    options = models.JSONField(
        default=list, blank=True,
        help_text='List of option strings for choice fields',
    )

    # Validation
    min_length = models.PositiveIntegerField(null=True, blank=True)
    max_length = models.PositiveIntegerField(null=True, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    # For scale field
    scale_min = models.PositiveSmallIntegerField(default=1)
    scale_max = models.PositiveSmallIntegerField(default=5)
    scale_min_label = models.CharField(max_length=50, blank=True)
    scale_max_label = models.CharField(max_length=50, blank=True)

    # File upload constraints
    max_file_size_mb = models.PositiveSmallIntegerField(default=10)
    allowed_file_types = models.JSONField(default=list, blank=True)

    # Location restriction
    is_location_restricted = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.form.title} — {self.label}"


class FormFieldLocationRestriction(models.Model):
    """
    Geographic restriction for a specific form field.
    If set, only users from the matching location can see/fill the field.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.OneToOneField(
        FormField,
        on_delete=models.CASCADE,
        related_name='location_restriction',
    )
    # Match any combination — leave blank to skip that level
    city = models.CharField(max_length=100, blank=True, help_text='e.g. Bangalore')
    state = models.CharField(max_length=100, blank=True, help_text='e.g. Karnataka')
    country = models.CharField(max_length=5, blank=True, help_text='ISO code e.g. IN')

    # Message shown to users outside the allowed zone
    restriction_message = models.CharField(
        max_length=500,
        default='This field is only available for users in a specific location.',
    )

    class Meta:
        verbose_name = 'Field Location Restriction'

    def __str__(self):
        parts = [p for p in [self.city, self.state, self.country] if p]
        return f"{self.field.label} → {', '.join(parts) or 'Any'}"

    def matches(self, city: str, state: str, country: str) -> bool:
        """Return True if the given location satisfies the restriction."""
        city_ok = (not self.city) or (self.city.lower() in (city or '').lower())
        state_ok = (not self.state) or (self.state.lower() in (state or '').lower())
        country_ok = (not self.country) or (self.country.upper() == (country or '').upper())
        return city_ok and state_ok and country_ok


# ──────────────────────────────────────────────────────────────────────────────
# Submissions
# ──────────────────────────────────────────────────────────────────────────────

class FormSubmission(models.Model):
    """A single completed form submission."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Respondent metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=5, blank=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)

    # Authenticated user (if form requires_auth)
    respondent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='form_submissions',
    )
    # Collected respondent identity (when form.requires_respondent_info=True)
    respondent_name = models.CharField(max_length=255, blank=True)
    respondent_email = models.EmailField(blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Submission #{self.id} for {self.form.title} at {self.submitted_at:%Y-%m-%d %H:%M}"


class SubmissionAnswer(models.Model):
    """A single field answer within a submission."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='answers')
    field = models.ForeignKey(FormField, on_delete=models.SET_NULL, null=True, related_name='answers')
    field_label = models.CharField(max_length=500, blank=True, help_text='Snapshot of label at submission time')
    field_type = models.CharField(max_length=30, blank=True)

    # Value storage — only one is populated based on field_type
    text_value = models.TextField(blank=True)
    number_value = models.FloatField(null=True, blank=True)
    json_value = models.JSONField(null=True, blank=True, help_text='For checkbox / multi-select')
    file_value = models.FileField(upload_to=submission_file_upload_path, null=True, blank=True)

    class Meta:
        ordering = ['submission__submitted_at']

    def __str__(self):
        return f"{self.field_label}: {self.text_value or self.number_value or '(file)'}"
