"""
Landing Pages — Models
========================
AI-generated and manually created landing pages served at /p/<slug>/
"""
import uuid
from django.db import models
from django.conf import settings


class LandingPageTemplate(models.Model):
    """Built-in templates for landing pages."""
    CATEGORY_CHOICES = [
        ('bio_link', 'Bio / Link Tree'),
        ('product', 'Product Page'),
        ('event', 'Event Page'),
        ('restaurant', 'Restaurant Menu'),
        ('portfolio', 'Portfolio'),
        ('contact', 'Contact / vCard'),
        ('custom', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='custom')
    description = models.TextField(blank=True, default='')
    thumbnail_url = models.URLField(blank=True, default='')
    html_template = models.TextField(help_text='Jinja2/Django template with {{ variables }}')
    css = models.TextField(blank=True, default='')
    default_config = models.JSONField(default=dict, help_text='Default variable values')
    is_active = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.category})"


class LandingPage(models.Model):
    """
    A landing page linked to a QR code, served publicly.
    Can be AI-generated or manually created from a template.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='landing_pages'
    )
    qr_code = models.ForeignKey(
        'qrcodes.QRCode', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='landing_pages'
    )
    template = models.ForeignKey(
        LandingPageTemplate, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=100, unique=True)
    meta_description = models.CharField(max_length=300, blank=True, default='')
    favicon_url = models.URLField(blank=True, default='')

    # Content
    html_content = models.TextField(help_text='Full HTML of the page')
    custom_css = models.TextField(blank=True, default='')
    custom_js = models.TextField(blank=True, default='', help_text='Optional JS — sanitized')

    # Configuration for template-based pages
    page_config = models.JSONField(default=dict, blank=True)

    # Branding
    show_qrgenie_badge = models.BooleanField(default=True)
    custom_domain = models.CharField(max_length=255, blank=True, default='')

    # AI
    is_ai_generated = models.BooleanField(default=False)
    ai_prompt = models.TextField(blank=True, default='')

    # Status
    is_published = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return self.title


# ── Popup (Feature 14) ───────────────────────────────
class Popup(models.Model):
    """
    Configurable popup/modal that can be embedded on landing pages or external sites.
    Supports 4 types: offer, form, video, timer.
    """
    class PopupType(models.TextChoices):
        OFFER   = 'offer',   'Offer / Promo'
        FORM    = 'form',    'Lead Capture Form'
        VIDEO   = 'video',   'Video Popup'
        TIMER   = 'timer',   'Countdown Timer'

    class TriggerType(models.TextChoices):
        ON_LOAD    = 'on_load',    'On Page Load'
        DELAY      = 'delay',      'After Delay'
        SCROLL     = 'scroll',     'On Scroll %'
        EXIT       = 'exit',       'Exit Intent'
        CLICK      = 'click',      'Button Click'

    class Position(models.TextChoices):
        CENTER     = 'center',      'Center Modal'
        BOTTOM     = 'bottom',      'Bottom Bar'
        TOP        = 'top',         'Top Bar'
        SLIDE_LEFT = 'slide_left',  'Slide-In Left'
        SLIDE_RIGHT= 'slide_right', 'Slide-In Right'
        FULLSCREEN = 'fullscreen',  'Fullscreen'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='popups',
    )
    landing_page = models.ForeignKey(
        LandingPage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='popups', help_text='Optionally link to a landing page',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )

    # Basic info
    name = models.CharField(max_length=300, help_text='Internal name for this popup')
    popup_type = models.CharField(max_length=20, choices=PopupType.choices, default=PopupType.OFFER)

    # Trigger & display
    trigger = models.CharField(max_length=20, choices=TriggerType.choices, default=TriggerType.DELAY)
    trigger_value = models.IntegerField(default=3, help_text='Seconds for delay, % for scroll, ignored for others')
    position = models.CharField(max_length=20, choices=Position.choices, default=Position.CENTER)
    show_overlay = models.BooleanField(default=True, help_text='Dark background overlay')
    allow_close = models.BooleanField(default=True, help_text='Show close button')
    show_once = models.BooleanField(default=True, help_text='Only show once per visitor (cookie-based)')
    frequency_hours = models.IntegerField(default=24, help_text='Hours before re-showing (if show_once=False)')

    # ─ CONTENT (stored as JSON for maximum flexibility) ─
    # Offer: { headline, body, cta_text, cta_url, image_url, discount_code }
    # Form:  { headline, body, fields: [{name, type, label, required}], submit_text, success_message }
    # Video: { headline, video_url, autoplay, allow_download }
    # Timer: { headline, body, target_date, cta_text, cta_url, expired_text }
    content = models.JSONField(default=dict, blank=True)

    # Styling (JSON) — { bg_color, text_color, accent_color, border_radius, width, font_family, custom_css }
    style = models.JSONField(default=dict, blank=True)

    # Analytics
    view_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    submit_count = models.PositiveIntegerField(default=0)

    # Status
    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)

    # Embed
    embed_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True,
                                    help_text='Token for embed script URL')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Popup'
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['embed_token']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_popup_type_display()})"

    @property
    def embed_url(self):
        from django.conf import settings
        base = getattr(settings, 'QR_BASE_REDIRECT_URL', 'http://localhost:8000')
        return f"{base}/popup/{self.embed_token}/embed.js"

    @property
    def conversion_rate(self):
        if self.view_count == 0:
            return 0.0
        return round((self.click_count + self.submit_count) / self.view_count * 100, 1)


class PopupSubmission(models.Model):
    """Stores form submissions from form-type popups."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    popup = models.ForeignKey(Popup, on_delete=models.CASCADE, related_name='submissions')
    data = models.JSONField(default=dict, help_text='Form field values')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    page_url = models.URLField(blank=True, default='', help_text='Page where form was submitted')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Popup Submission'

    def __str__(self):
        return f"Submission for {self.popup.name} at {self.created_at}"
