"""
QR Codes Models
================
Full CRUD, versioning, rules, file delivery, password protection.
"""
import uuid
import string
import random
from django.db import models
from django.conf import settings
from apps.core.models import Organization, User, SoftDeleteMixin


def generate_slug(length=8):
    """Generate a unique short slug for QR codes."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))


# ── QR Code ────────────────────────────────────────────
class QRCode(SoftDeleteMixin, models.Model):
    """Core QR code entity with dynamic routing."""

    class QRType(models.TextChoices):
        URL = 'url', 'Direct URL'
        MULTI_LINK = 'multi_link', 'Multi-Link Page'
        LANDING_PAGE = 'landing_page', 'AI Landing Page'
        FILE = 'file', 'File Download'
        PAYMENT = 'payment', 'Payment QR'
        CHAT = 'chat', 'Chat QR'
        WIFI = 'wifi', 'WiFi QR'
        VCARD = 'vcard', 'vCard Contact'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        EXPIRED = 'expired', 'Expired'
        ARCHIVED = 'archived', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='qr_codes')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='qr_codes')

    # Identity
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=50, unique=True, default=generate_slug, db_index=True)
    description = models.TextField(blank=True)
    qr_type = models.CharField(max_length=20, choices=QRType.choices, default=QRType.URL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Destination
    destination_url = models.URLField(max_length=2048, blank=True, null=True, help_text='Primary destination URL')
    fallback_url = models.URLField(max_length=2048, blank=True, null=True, help_text='Fallback URL when no rules match')

    # Static vs Dynamic
    is_dynamic = models.BooleanField(default=True, help_text='Dynamic QR encodes redirect URL; static encodes raw content')
    static_content = models.TextField(blank=True, help_text='Raw content for static QR (URL, text, vCard, WiFi, etc.)')

    # QR Image Customization
    qr_image_url = models.URLField(blank=True, null=True, help_text='Stored QR image URL')
    foreground_color = models.CharField(max_length=7, default='#000000')
    background_color = models.CharField(max_length=7, default='#FFFFFF')
    logo_url = models.URLField(blank=True, null=True, help_text='Center logo overlay')
    error_correction = models.CharField(max_length=1, default='M', choices=[
        ('L', 'Low (7%)'), ('M', 'Medium (15%)'), ('Q', 'Quartile (25%)'), ('H', 'High (30%)'),
    ])

    # Module Style & Gradient
    module_style = models.CharField(max_length=20, default='square', choices=[
        ('square', 'Square'), ('rounded', 'Rounded'), ('circle', 'Circle'),
        ('gapped', 'Gapped Square'), ('vertical_bars', 'Vertical Bars'), ('horizontal_bars', 'Horizontal Bars'),
    ])
    gradient_type = models.CharField(max_length=20, default='none', choices=[
        ('none', 'No Gradient'), ('linear_h', 'Horizontal'), ('linear_v', 'Vertical'),
        ('radial', 'Radial'), ('square', 'Square'),
    ])
    gradient_start_color = models.CharField(max_length=7, blank=True, help_text='Gradient start colour')
    gradient_end_color = models.CharField(max_length=7, blank=True, help_text='Gradient end colour')

    # Frame / CTA
    frame_style = models.CharField(max_length=30, default='none', choices=[
        ('none', 'No Frame'), ('banner_bottom', 'Banner Bottom'), ('banner_top', 'Banner Top'),
        ('rounded_box', 'Rounded Box'), ('ticket', 'Ticket'),
    ])
    frame_color = models.CharField(max_length=7, default='#000000')
    frame_text = models.CharField(max_length=100, blank=True, help_text='CTA text e.g. "Scan Me"')
    frame_text_color = models.CharField(max_length=7, default='#FFFFFF')

    # Protection
    password_hash = models.CharField(max_length=128, blank=True, null=True, help_text='bcrypt hash')
    is_password_protected = models.BooleanField(default=False)

    # Limits & Expiry
    expires_at = models.DateTimeField(null=True, blank=True)
    scan_limit = models.IntegerField(null=True, blank=True, help_text='Max total scans allowed')
    total_scans = models.IntegerField(default=0)
    unique_scans = models.IntegerField(default=0)

    # Tags & Metadata
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    folder = models.CharField(max_length=255, blank=True, default='')

    # UTM Parameters (Feature 42)
    utm_source = models.CharField(max_length=255, blank=True, default='')
    utm_medium = models.CharField(max_length=255, blank=True, default='')
    utm_campaign = models.CharField(max_length=255, blank=True, default='')

    # Animated QR (Feature 43)
    animation_glow = models.BooleanField(default=False, help_text='Enable glow edge animation')
    glow_color = models.CharField(max_length=7, default='#22D3EE', help_text='Glow colour hex')
    glow_intensity = models.PositiveSmallIntegerField(default=2, help_text='Glow intensity 1-5')
    gif_background_url = models.URLField(max_length=2048, blank=True, default='', help_text='GIF background behind QR')

    # Versioning
    current_version = models.IntegerField(default=1)

    # Freeze mode (Feature 38)
    is_frozen = models.BooleanField(default=False, help_text='Locked — only owner/admin can edit')
    frozen_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='frozen_qr_codes')
    frozen_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['slug']),
            models.Index(fields=['status']),
            models.Index(fields=['status', 'organization']),  # Active QR filter
        ]

    def __str__(self):
        return f"{self.title} ({self.slug})"

    @property
    def short_url(self):
        return f"{settings.QR_BASE_REDIRECT_URL}/{self.slug}"

    def is_expired(self):
        from django.utils import timezone
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        if self.scan_limit and self.total_scans >= self.scan_limit:
            return True
        return False


# ── QR Version (history) ──────────────────────────────
class QRVersion(models.Model):
    """Stores version history for QR code changes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    snapshot = models.JSONField(help_text='Full QR state at this version')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    change_summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ['qr_code', 'version_number']


# ── Routing Rule ──────────────────────────────────────
class RoutingRule(models.Model):
    """Conditional routing rules for QR redirect logic."""

    class RuleType(models.TextChoices):
        DEVICE = 'device', 'Device Type'
        GEO = 'geo', 'Geographic Location'
        TIME = 'time', 'Time Schedule'
        LANGUAGE = 'language', 'Browser Language'
        GPS_RADIUS = 'gps_radius', 'GPS Radius (Geofence)'
        AB_TEST = 'ab_test', 'A/B Test'
        URL_PARAM = 'url_param', 'URL Parameter'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='rules')
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    priority = models.IntegerField(default=0, help_text='Higher priority rules evaluated first')
    is_active = models.BooleanField(default=True)

    # Rule configuration (flexible JSON)
    conditions = models.JSONField(default=dict, help_text='''
        Examples:
        device: {"device_type": "mobile", "os": "android"}
        geo: {"country": "IN", "city": "Bengaluru"}
        time: {"start": "09:00", "end": "18:00", "timezone": "Asia/Kolkata", "days": ["mon","tue"]}
        language: {"languages": ["en", "hi"]}
        gps_radius: {"lat": 12.97, "lon": 77.59, "radius_meters": 500}
        ab_test: {"variant": "A", "weight": 50}
        url_param: {"key": "src", "value": "instagram"}
    ''')

    # Destination when rule matches
    destination_url = models.URLField(max_length=2048)
    label = models.CharField(max_length=255, blank=True, help_text='Human-readable rule label')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'created_at']

    def __str__(self):
        return f"{self.rule_type} → {self.destination_url[:50]}"


# ── Multi-Link Item ───────────────────────────────────
class MultiLinkItem(models.Model):
    """Individual links in a multi-link QR bio page."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='multi_links')
    title = models.CharField(max_length=255)
    url = models.URLField(max_length=2048)
    icon = models.CharField(max_length=50, blank=True, help_text='Icon name e.g. globe, instagram, youtube')
    thumbnail_url = models.URLField(blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    click_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order']


# ── File Attachment ───────────────────────────────────
class FileAttachment(models.Model):
    """Files attached to file-type QR codes with versioning."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='files')
    file_name = models.CharField(max_length=500)
    file_url = models.URLField(max_length=2048)
    file_size = models.BigIntegerField(default=0, help_text='Size in bytes')
    mime_type = models.CharField(max_length=100, blank=True)
    version = models.IntegerField(default=1)
    is_current = models.BooleanField(default=True)
    download_count = models.IntegerField(default=0)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']


# ── Payment Config ────────────────────────────────────
class PaymentConfig(models.Model):
    """Payment gateway config for payment-type QR codes."""

    class Gateway(models.TextChoices):
        UPI = 'upi', 'UPI'
        STRIPE = 'stripe', 'Stripe'
        RAZORPAY = 'razorpay', 'Razorpay'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='payment_config')
    gateway = models.CharField(max_length=20, choices=Gateway.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')
    # UPI-specific
    upi_id = models.CharField(max_length=255, blank=True)
    # Stripe/Razorpay payment link
    payment_link = models.URLField(blank=True, null=True)
    merchant_name = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ── Chat Config ───────────────────────────────────────
class ChatConfig(models.Model):
    """Chat platform config for chat-type QR codes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='chat_config')
    whatsapp_number = models.CharField(max_length=20, blank=True)
    whatsapp_message = models.TextField(blank=True, help_text='Pre-filled message')
    telegram_username = models.CharField(max_length=100, blank=True)
    messenger_page_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ── Rotation Schedule ─────────────────────────────────
class RotationSchedule(models.Model):
    """
    Auto-rotating landing pages for a QR code.
    Redirects change automatically based on day/week/date range.
    """

    class RotationType(models.TextChoices):
        DAILY  = 'daily',  'Daily (cycles through list each day)'
        WEEKLY = 'weekly', 'Weekly (one page per day-of-week)'
        CUSTOM = 'custom', 'Custom (date range per page)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='rotation_schedule',
    )
    is_active = models.BooleanField(default=True)
    rotation_type = models.CharField(
        max_length=20, choices=RotationType.choices, default=RotationType.DAILY,
    )
    tz = models.CharField(max_length=50, default='UTC', help_text='IANA timezone e.g. Asia/Kolkata')

    # pages — ordered list of entries. Shape depends on rotation_type:
    #  daily:  [{"page_url":"...","label":"Page A"}, ...]
    #  weekly: [{"page_url":"...","label":"Mon","day_of_week":0}, ...]
    #  custom: [{"page_url":"...","label":"Camp A","start_date":"2026-02-01","end_date":"2026-02-07"}, ...]
    pages = models.JSONField(default=list, help_text='Ordered page entries for rotation')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Rotation Schedule'

    def __str__(self):
        return f"Rotation({self.rotation_type}) for {self.qr_code.slug}"


# ── Language Routes (Feature 8) ──────────────────────
class LanguageRoute(models.Model):
    """
    Per-QR language→URL mapping for auto-detected redirect.
    When a user scans, the redirect engine parses Accept-Language, optionally
    checks GeoIP for country→language fallback, and picks the best match.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='language_route')
    is_active = models.BooleanField(default=True)

    # JSON list of {lang, url, label?} ordered by priority (first = highest)
    # Shape: [{"lang":"en","url":"https://…","label":"English"}, {"lang":"hi","url":"…","label":"Hindi"}, ...]
    routes = models.JSONField(default=list, help_text='Ordered language→URL mappings')

    # Default URL when no language matches (empty = falls through to QR destination)
    default_url = models.URLField(max_length=2048, blank=True,
                                  help_text='Fallback URL when no language matches')

    # Geo→language fallback mapping (optional). Shape: {"IN":"hi","DE":"de","JP":"ja"}
    # If Accept-Language has no match but GeoIP country is in this map, use the mapped language.
    geo_fallback = models.JSONField(default=dict, blank=True,
                                    help_text='Country code→language fallback map')

    # Direct geo→URL mappings (district/city level). Checked BEFORE language routes.
    # Shape: [{"country":"IN","state":"AP","district":"Visakhapatnam","url":"https://…","label":"Vizag"}, ...]
    # "district" is optional — entries without it match at state level.
    geo_direct = models.JSONField(default=list, blank=True,
                                  help_text='Direct geo→URL: [{country,state,district?,url,label?}]')

    # Whether to use quality weights from Accept-Language (RFC 2616 §14.4)
    use_quality_weights = models.BooleanField(default=True,
                                              help_text='Use q= weights from Accept-Language header')

    # Mandatory GPS location mode: first scan requires GPS permission; device IP+coords cached after.
    mandatory_location = models.BooleanField(default=False,
                                             help_text='Require GPS on first scan; cache device IP→coords for repeat scans')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Language Route'

    def __str__(self):
        langs = [r.get('lang', '?') for r in (self.routes or [])[:5]]
        return f"Lang({','.join(langs)}) for {self.qr_code.slug}"


# ── Time Schedule (Feature 9) ─────────────────────────
class TimeSchedule(models.Model):
    """
    Time-based redirects for a QR code.
    Different URLs served at different times of day (e.g. breakfast / lunch / dinner menus).
    Rules are evaluated in order; first match wins.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='time_schedule',
    )
    is_active = models.BooleanField(default=True)
    tz = models.CharField(max_length=50, default='UTC', help_text='IANA timezone e.g. Asia/Kolkata')

    # rules — ordered list of time windows.
    # Shape: [
    #   {
    #     "label": "Breakfast Menu",
    #     "url": "https://example.com/breakfast",
    #     "start_time": "06:00",
    #     "end_time": "11:00",
    #     "days": ["mon","tue","wed","thu","fri","sat","sun"]
    #   },
    #   ...
    # ]
    # "days" is optional — empty/missing means every day.
    rules = models.JSONField(default=list, help_text='Ordered time-window rules')

    # Fallback URL when no time rule matches (empty → falls through to QR destination)
    default_url = models.URLField(max_length=2048, blank=True,
                                  help_text='Fallback URL when no time rule matches')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Time Schedule'

    def __str__(self):
        count = len(self.rules) if self.rules else 0
        return f"TimeSchedule({count} rules) for {self.qr_code.slug}"


# ── Device Location Cache ─────────────────────────────
class DeviceLocationCache(models.Model):
    """
    Caches a device's GPS coordinates keyed by public IP address.
    After a user allows location permission once (mandatory GPS mode),
    their IP → lat/lng is stored here so future scans skip the GPS prompt.
    """
    ip_address = models.GenericIPAddressField(db_index=True, unique=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Device Location Cache'

    def __str__(self):
        return f"{self.ip_address} → ({self.latitude:.4f}, {self.longitude:.4f})"


# ── PDF Document (Feature 11) ─────────────────────────
class PDFDocument(models.Model):
    """
    Inline PDF viewer document attached to a QR code.
    When scanned, the QR opens an embedded PDF.js viewer instead of downloading.
    Uses signed access tokens for secure, time-limited sharing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='pdf_document',
    )
    # File info
    original_filename = models.CharField(max_length=500, help_text='Original uploaded filename')
    file_path = models.CharField(max_length=1024, help_text='Relative path under MEDIA_ROOT')
    file_size = models.BigIntegerField(default=0, help_text='Size in bytes')
    mime_type = models.CharField(max_length=100, default='application/pdf')
    page_count = models.IntegerField(default=0, help_text='Number of PDF pages (0=unknown)')

    # Signed access token for public viewer
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True,
                                     help_text='Signed token for public viewer URL')

    # Viewer settings
    is_active = models.BooleanField(default=True)
    allow_download = models.BooleanField(default=False,
                                          help_text='Show download button in viewer')
    title = models.CharField(max_length=500, blank=True,
                              help_text='Display title in viewer (defaults to filename)')

    # Analytics
    view_count = models.IntegerField(default=0)

    # Timestamps
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'PDF Document'

    def __str__(self):
        return f"PDF({self.original_filename}) for {self.qr_code.slug}"

    @property
    def viewer_url(self):
        """Public viewer URL (no auth required, token-secured)."""
        from django.conf import settings
        base = getattr(settings, 'SITE_BASE_URL', 'http://localhost:8000')
        return f"{base}/pdf/{self.access_token}/"

    def regenerate_token(self):
        """Generate new access token (invalidates old links)."""
        self.access_token = uuid.uuid4()
        self.save(update_fields=['access_token'])


# ── Video Document (Feature 13) ───────────────────────
class VideoDocument(models.Model):
    """
    Inline video player attached to a QR code.
    When scanned, the QR opens a Video.js HTML5 player page.
    Uses signed access tokens for secure sharing (same pattern as PDFDocument).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='video_document',
    )
    # File info
    original_filename = models.CharField(max_length=500, help_text='Original uploaded filename')
    file_path = models.CharField(max_length=1024, help_text='Relative path under MEDIA_ROOT')
    file_size = models.BigIntegerField(default=0, help_text='Size in bytes')
    mime_type = models.CharField(max_length=100, default='video/mp4')
    duration_seconds = models.FloatField(default=0, help_text='Duration in seconds (0=unknown)')

    # Signed access token for public player
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True,
                                     help_text='Signed token for public player URL')

    # Player settings
    is_active = models.BooleanField(default=True)
    allow_download = models.BooleanField(default=False,
                                          help_text='Show download button in player')
    autoplay = models.BooleanField(default=False, help_text='Auto-play on page load')
    loop = models.BooleanField(default=False, help_text='Loop video playback')
    title = models.CharField(max_length=500, blank=True,
                              help_text='Display title in player (defaults to filename)')
    # Optional thumbnail
    thumbnail_path = models.CharField(max_length=1024, blank=True,
                                       help_text='Relative path to poster/thumbnail image')

    # Analytics
    view_count = models.IntegerField(default=0)

    # Timestamps
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Video Document'

    def __str__(self):
        return f"Video({self.original_filename}) for {self.qr_code.slug}"

    @property
    def player_url(self):
        """Public player URL (no auth required, token-secured)."""
        from django.conf import settings
        base = getattr(settings, 'SITE_BASE_URL', 'http://localhost:8000')
        return f"{base}/video/{self.access_token}/"

    def regenerate_token(self):
        """Generate new access token (invalidates old links)."""
        self.access_token = uuid.uuid4()
        self.save(update_fields=['access_token'])


# ── Device Route (Feature 15) ─────────────────────────
class DeviceRoute(models.Model):
    """
    Device-based redirects for a QR code.
    Detects the scanning device's OS/platform via User-Agent and redirects
    to the appropriate URL (e.g. App Store for iOS, Play Store for Android).

    Uses ua-parser-python for robust device detection.
    Rules are evaluated in platform priority order; first match wins.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='device_route',
    )
    is_active = models.BooleanField(default=True)

    # Per-platform destination URLs (blank = skip / fall through)
    android_url = models.URLField(max_length=2048, blank=True, default='',
                                   help_text='Redirect URL for Android devices')
    ios_url = models.URLField(max_length=2048, blank=True, default='',
                               help_text='Redirect URL for iOS devices (iPhone/iPad)')
    windows_url = models.URLField(max_length=2048, blank=True, default='',
                                   help_text='Redirect URL for Windows devices')
    mac_url = models.URLField(max_length=2048, blank=True, default='',
                               help_text='Redirect URL for macOS devices')
    linux_url = models.URLField(max_length=2048, blank=True, default='',
                                 help_text='Redirect URL for Linux devices')
    tablet_url = models.URLField(max_length=2048, blank=True, default='',
                                  help_text='Redirect URL specifically for tablets (iPad, Android tablet)')
    default_url = models.URLField(max_length=2048, blank=True, default='',
                                   help_text='Fallback URL when no device rule matches')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Device Route'

    def __str__(self):
        platforms = []
        if self.android_url: platforms.append('Android')
        if self.ios_url: platforms.append('iOS')
        if self.windows_url: platforms.append('Windows')
        if self.mac_url: platforms.append('Mac')
        if self.tablet_url: platforms.append('Tablet')
        return f"DeviceRoute({','.join(platforms) or 'empty'}) for {self.qr_code.slug}"


# ── GPS Radius / Geo-Fence (Feature 17) ───────────────
class GeoFenceRule(models.Model):
    """
    GPS-radius geo-fencing for a QR code.

    Each QR can have one GeoFenceRule containing multiple zones.
    When scanned, the browser requests GPS permission; coordinates are
    sent to the backend which checks if the user falls within any zone
    using the Haversine formula.

    zones — ordered list of geo-fence circles:
      [
        {
          "label": "Main Office",
          "lat": 12.9716,
          "lng": 77.5946,
          "radius_meters": 200,
          "url": "https://example.com/office-menu"
        },
        ...
      ]
    First matching zone wins.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='geo_fence',
    )
    is_active = models.BooleanField(default=True)

    zones = models.JSONField(default=list,
                             help_text='Ordered list of geo-fence zones [{label, lat, lng, radius_meters, url}]')

    # Fallback URL when user is outside all zones (empty → falls through to QR destination)
    default_url = models.URLField(max_length=2048, blank=True, default='',
                                  help_text='Fallback URL when user is outside all zones')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Geo-Fence Rule'

    def __str__(self):
        count = len(self.zones) if self.zones else 0
        return f"GeoFence({count} zones) for {self.qr_code.slug}"


# ── A/B Split Test (Feature 18) ───────────────────────
class ABTest(models.Model):
    """
    A/B split testing for a QR code.

    Each QR can have one ABTest containing multiple variants.
    Traffic is randomly assigned based on configured weight percentages.
    Cookie stickiness ensures repeating visitors always see the same variant.

    variants — list of variant configs:
      [
        {"label": "Page A", "url": "https://example.com/page-a", "weight": 50},
        {"label": "Page B", "url": "https://example.com/page-b", "weight": 50},
        ...
      ]
    Weights should sum to 100, but the engine normalises them if they don't.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='ab_test',
    )
    is_active = models.BooleanField(default=True)

    variants = models.JSONField(
        default=list,
        help_text='Ordered list of variants [{label, url, weight}]',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'A/B Split Test'

    def __str__(self):
        count = len(self.variants) if self.variants else 0
        return f"ABTest({count} variants) for {self.qr_code.slug}"


# ── App Deep Link (Feature 19) ────────────────────────
class DeepLink(models.Model):
    """
    App deep linking for a QR code.

    Detects the visitor's OS from User-Agent and redirects to the
    appropriate deep link:
      • iOS → Universal Link or custom URI scheme, with App Store fallback
      • Android → App Link or custom URI scheme, with Play Store fallback
      • Desktop/other → fallback_url

    The redirect engine serves an intermediate HTML page that attempts
    the deep link first, then falls back after a short timeout.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='deep_link',
    )
    is_active = models.BooleanField(default=True)

    # ── iOS ──
    ios_deep_link = models.URLField(
        max_length=2048, blank=True, default='',
        help_text='iOS Universal Link (https://...) or custom URI scheme (myapp://...)',
    )
    ios_fallback_url = models.URLField(
        max_length=2048, blank=True, default='',
        help_text='Fallback URL if app is not installed (e.g. App Store link)',
    )

    # ── Android ──
    android_deep_link = models.URLField(
        max_length=2048, blank=True, default='',
        help_text='Android App Link (https://...) or custom URI scheme (myapp://...)',
    )
    android_fallback_url = models.URLField(
        max_length=2048, blank=True, default='',
        help_text='Fallback URL if app is not installed (e.g. Play Store link)',
    )

    # ── Custom URI scheme (cross-platform) ──
    custom_uri = models.CharField(
        max_length=2048, blank=True, default='',
        help_text='Custom URI scheme e.g. myapp://path/to/content',
    )

    # ── Desktop / other fallback ──
    fallback_url = models.URLField(
        max_length=2048, blank=True, default='',
        help_text='Fallback for desktop or when no platform matches',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'App Deep Link'

    def __str__(self):
        parts = []
        if self.ios_deep_link: parts.append('iOS')
        if self.android_deep_link: parts.append('Android')
        if self.custom_uri: parts.append('URI')
        return f"DeepLink({','.join(parts) or 'empty'}) for {self.qr_code.slug}"


# ── Short-Lived Token Redirect (Feature 20) ──────────
class TokenRedirect(models.Model):
    """
    Short-lived token redirect configuration for a QR code.

    When active, scans generate a JWT token link that expires
    after a configurable TTL. Supports three modes:

      • timed          — token valid for N seconds (default 60)
      • single_use     — token can only be redeemed once
      • limited_sessions — token can be redeemed up to max_uses times

    The redirect engine gates access: no valid token → generate JWT →
    redirect to /r/SLUG/?token=JWT. The JWT is validated on return.
    Expired / used tokens show a "Link Expired" page.

    JWT is signed with Django SECRET_KEY using PyJWT (HS256).
    """

    class Mode(models.TextChoices):
        TIMED = 'timed', 'Time-limited'
        SINGLE_USE = 'single_use', 'Single Use'
        LIMITED_SESSIONS = 'limited_sessions', 'Limited Sessions'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='token_redirect',
    )
    is_active = models.BooleanField(default=True)
    mode = models.CharField(
        max_length=20, choices=Mode.choices, default=Mode.TIMED,
    )
    ttl_seconds = models.IntegerField(
        default=60,
        help_text='Token lifetime in seconds (e.g. 60 = 1 minute)',
    )
    max_uses = models.IntegerField(
        default=1,
        help_text='Max redemptions per token (applies to single_use and limited_sessions)',
    )
    first_used_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Set on first scan — used for timed-mode QR-level expiry',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Token Redirect'

    def __str__(self):
        return f"TokenRedirect({self.mode}, {self.ttl_seconds}s) for {self.qr_code.slug}"


class TokenUsage(models.Model):
    """
    Records each time a JWT token is redeemed, enabling
    single-use and limited-session enforcement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_redirect = models.ForeignKey(
        TokenRedirect, on_delete=models.CASCADE, related_name='usages',
    )
    jti = models.CharField(max_length=64, db_index=True, help_text='JWT ID — unique per token')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    session_key = models.CharField(max_length=128, blank=True, default='')
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']

    def __str__(self):
        return f"TokenUsage(jti={self.jti[:12]}…) at {self.used_at}"


# ── Expiry-Based QR (Feature 21) ─────────────────────
class QRExpiry(models.Model):
    """
    Expiry configuration for a QR code.

    Supports three expiry modes:
      • date       — QR expires at end of a given date (23:59:59)
      • datetime   — QR expires at an exact date & time
      • scan_count — QR expires after N total scans

    When the QR is scanned past its limit, the redirect engine shows
    an "Expired" page (or redirects to expired_redirect_url if set).
    """

    class ExpiryType(models.TextChoices):
        DATE = 'date', 'Expire by Date'
        DATETIME = 'datetime', 'Expire by Date & Time'
        SCAN_COUNT = 'scan_count', 'Expire by Scan Count'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(
        QRCode, on_delete=models.CASCADE, related_name='expiry',
    )
    is_active = models.BooleanField(default=True)
    expiry_type = models.CharField(
        max_length=20, choices=ExpiryType.choices, default=ExpiryType.DATE,
    )

    # Date-based expiry
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text='QR expires at end of this date (23:59:59 server time)',
    )

    # DateTime-based expiry
    expiry_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text='QR expires at this exact date & time',
    )

    # Scan-count expiry
    max_scans = models.PositiveIntegerField(
        default=100,
        help_text='Maximum number of scans before QR expires',
    )
    scan_count = models.PositiveIntegerField(
        default=0,
        help_text='Current number of scans counted',
    )

    # Optional: where to redirect when expired
    expired_redirect_url = models.URLField(
        max_length=2048, blank=True,
        help_text='Redirect to this URL when expired (blank = show expiry page)',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'QR Expiry'
        verbose_name_plural = 'QR Expiries'

    def __str__(self):
        return f"QRExpiry({self.expiry_type}) for {self.qr_code.slug}"

    def is_expired(self):
        """Return True if the QR should be considered expired."""
        if not self.is_active:
            return False
        from django.utils import timezone
        from datetime import datetime, time

        if self.expiry_type == 'date' and self.expiry_date:
            # Expired after the end of the specified date
            end_of_day = timezone.make_aware(
                datetime.combine(self.expiry_date, time(23, 59, 59)),
            )
            return timezone.now() > end_of_day

        if self.expiry_type == 'datetime' and self.expiry_datetime:
            return timezone.now() > self.expiry_datetime

        if self.expiry_type == 'scan_count':
            return self.scan_count >= self.max_scans

        return False

    def increment_scan(self):
        """Atomically increment scan_count."""
        from django.db.models import F
        QRExpiry.objects.filter(pk=self.pk).update(scan_count=F('scan_count') + 1)
        self.refresh_from_db()


# ── Scan Alert (Feature 25) ──────────────────────────
class ScanAlert(models.Model):
    """
    Email notification alerts triggered by QR scan events.
    Each QR code can have one alert config.
    """
    class AlertEvent(models.TextChoices):
        EVERY_SCAN = 'every_scan', 'Every Scan'
        MILESTONE = 'milestone', 'Milestone (N scans)'
        FIRST_SCAN = 'first_scan', 'First Scan'
        SCAN_SPIKE = 'scan_spike', 'Scan Spike'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='scan_alert')
    is_active = models.BooleanField(default=True)

    # Which events trigger the alert
    alert_events = models.JSONField(
        default=list,
        help_text='List of event types: every_scan, milestone, first_scan, scan_spike',
    )

    # Email recipients (comma-separated)
    email_recipients = models.TextField(
        blank=True,
        help_text='Comma-separated email addresses to notify',
    )

    # Milestone threshold
    milestone_every = models.IntegerField(
        default=100,
        help_text='Send alert every N scans (for milestone event)',
    )

    # Spike detection: alert if scans in last N minutes exceed threshold
    spike_window_minutes = models.IntegerField(default=60)
    spike_threshold = models.IntegerField(
        default=50,
        help_text='Alert if scans exceed this count within the window',
    )

    # Throttling — minimum minutes between notifications (prevent spam)
    cooldown_minutes = models.IntegerField(
        default=5,
        help_text='Min minutes between alerts to prevent spam',
    )
    last_notified_at = models.DateTimeField(null=True, blank=True)

    # Stats
    total_alerts_sent = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"ScanAlert: {self.qr_code.title}"


# ── Loyalty Point QR (Feature 26) ─────────────────────
class LoyaltyProgram(models.Model):
    """
    Loyalty point configuration for a QR code.
    Each scan earns the scanner points.  Points are tracked per
    identifier (email / phone) that the user supplies on first scan.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='loyalty_program')
    is_active = models.BooleanField(default=True)

    program_name = models.CharField(max_length=200, default='Loyalty Rewards')
    points_per_scan = models.IntegerField(default=1, help_text='Points awarded per scan')
    max_points_per_day = models.IntegerField(default=10, help_text='Max points a single member can earn per day (0 = unlimited)')
    bonus_points = models.IntegerField(default=0, help_text='Extra bonus points on first scan')

    # Reward tiers — JSON list of {name, points_required, description}
    reward_tiers = models.JSONField(
        default=list,
        help_text='List of reward tiers: [{name, points_required, description}]',
    )

    # Stats
    total_members = models.IntegerField(default=0)
    total_points_issued = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Loyalty: {self.qr_code.title} — {self.program_name}"


class LoyaltyMember(models.Model):
    """
    A member (identified by email or phone) enrolled in a QR loyalty program.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    program = models.ForeignKey(LoyaltyProgram, on_delete=models.CASCADE, related_name='members')
    identifier = models.CharField(max_length=255, help_text='Email or phone number')
    name = models.CharField(max_length=200, blank=True)
    points = models.IntegerField(default=0)
    total_scans = models.IntegerField(default=0)
    last_scan_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-points']
        unique_together = [('program', 'identifier')]

    def __str__(self):
        return f"{self.identifier}: {self.points} pts"


# ── Digital vCard (Feature 28) ────────────────────────
class DigitalVCard(models.Model):
    """
    Digital business card data linked to a QR code.
    When scanned, shows a beautiful contact card page with download-as-VCF.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='vcard')
    is_active = models.BooleanField(default=True)

    # Name
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    prefix = models.CharField(max_length=20, blank=True, help_text='e.g. Dr., Mr., Mrs.')
    suffix = models.CharField(max_length=20, blank=True, help_text='e.g. Jr., PhD')

    # Professional
    organization = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200, blank=True, help_text='Job title')
    department = models.CharField(max_length=200, blank=True)

    # Contact
    email = models.EmailField(blank=True)
    email_work = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    phone_work = models.CharField(max_length=30, blank=True)
    phone_cell = models.CharField(max_length=30, blank=True)

    # Web
    website = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    twitter = models.CharField(max_length=100, blank=True)
    github = models.URLField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)

    # Address
    street = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)

    # Appearance
    photo_url = models.URLField(blank=True, help_text='Profile photo URL')
    accent_color = models.CharField(max_length=7, default='#6366f1', help_text='Hex color for card accent')
    bio = models.TextField(blank=True, max_length=500)

    # Notes
    note = models.TextField(blank=True, max_length=1000)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def full_name(self):
        parts = [self.prefix, self.first_name, self.last_name, self.suffix]
        return ' '.join(p for p in parts if p).strip()

    def __str__(self):
        return f"vCard: {self.full_name()} ({self.qr_code.title})"


# ── Product Authentication (Feature 31) ───────────────
class ProductAuth(models.Model):
    """Product authentication config linked to a QR code."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='product_auth')
    is_active = models.BooleanField(default=True)

    product_name = models.CharField(max_length=255, blank=True)
    manufacturer = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True, max_length=1000)
    product_image_url = models.URLField(blank=True)
    secret_key = models.CharField(max_length=128, help_text='HMAC secret for signing serials')

    # Branding
    brand_color = models.CharField(max_length=7, default='#22c55e')
    support_url = models.URLField(blank=True)
    support_email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ProductAuth: {self.product_name} ({self.qr_code.title})"


class ProductSerial(models.Model):
    """Individual serial number with HMAC signature."""

    class VerifyStatus(models.TextChoices):
        UNSCANNED = 'unscanned', 'Unscanned'
        VERIFIED = 'verified', 'Verified'
        FLAGGED = 'flagged', 'Flagged'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_auth = models.ForeignKey(ProductAuth, on_delete=models.CASCADE, related_name='serials')
    serial_number = models.CharField(max_length=64, db_index=True)
    hmac_signature = models.CharField(max_length=128)
    status = models.CharField(max_length=20, choices=VerifyStatus.choices, default=VerifyStatus.UNSCANNED)
    batch_label = models.CharField(max_length=100, blank=True)
    manufactured_date = models.DateField(null=True, blank=True)

    # Scan tracking
    total_scans = models.PositiveIntegerField(default=0)
    first_scanned_at = models.DateTimeField(null=True, blank=True)
    last_scanned_at = models.DateTimeField(null=True, blank=True)
    last_scanned_ip = models.GenericIPAddressField(null=True, blank=True)
    last_scanned_location = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['product_auth', 'serial_number']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.serial_number} ({self.product_auth.product_name})"


# ── Document Upload Form (Feature 33) ─────────────────
class DocumentUploadForm(models.Model):
    """Document-upload form config linked to a QR code."""

    class AllowedType(models.TextChoices):
        PHOTOS = 'photos', 'Photos'
        ID_PROOFS = 'id_proofs', 'ID Proofs'
        KYC = 'kyc', 'KYC Files'
        CERTIFICATES = 'certificates', 'Certificates'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='doc_upload_form')
    is_active = models.BooleanField(default=True)

    title = models.CharField(max_length=255, blank=True, default='Upload Documents')
    description = models.TextField(blank=True, max_length=1000)
    allowed_types = models.JSONField(
        default=list,
        help_text='List of allowed category tags: photos, id_proofs, kyc, certificates, other',
    )
    allowed_extensions = models.CharField(
        max_length=500, blank=True,
        default='.jpg,.jpeg,.png,.pdf,.heic,.webp',
        help_text='Comma-separated file extensions',
    )
    max_file_size_mb = models.PositiveIntegerField(default=10, help_text='Per-file limit in MB')
    max_files = models.PositiveIntegerField(default=5, help_text='Max files per submission')
    require_name = models.BooleanField(default=True)
    require_email = models.BooleanField(default=False)
    require_phone = models.BooleanField(default=False)
    success_message = models.CharField(max_length=500, blank=True, default='Documents uploaded successfully!')
    brand_color = models.CharField(max_length=7, default='#6366f1')
    notify_email = models.CharField(max_length=255, blank=True, help_text='Email for new-submission notifications')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DocUploadForm: {self.title} ({self.qr_code.title})"


class DocumentSubmission(models.Model):
    """A single submission (one person uploading files)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(DocumentUploadForm, on_delete=models.CASCADE, related_name='submissions')
    submitter_name = models.CharField(max_length=255, blank=True)
    submitter_email = models.EmailField(blank=True)
    submitter_phone = models.CharField(max_length=30, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Submission by {self.submitter_name or 'Anonymous'} @ {self.created_at:%Y-%m-%d %H:%M}"


class DocumentFile(models.Model):
    """Individual file in a submission."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(DocumentSubmission, on_delete=models.CASCADE, related_name='files')
    original_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=1024, help_text='Relative path under MEDIA_ROOT')
    file_size = models.PositiveIntegerField(default=0, help_text='Bytes')
    mime_type = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, blank=True, help_text='photos / id_proofs / kyc / etc.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.original_name


# ── Funnel Config (Feature 34) ───────────────────────
class FunnelConfig(models.Model):
    """Multi-step funnel / landing-page journey attached to a QR code."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name='funnel_config')
    is_active = models.BooleanField(default=True)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    brand_color = models.CharField(max_length=20, blank=True, default='#6366f1')
    show_progress_bar = models.BooleanField(default=True)
    allow_back_navigation = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Funnel: {self.title or self.qr_code.title}"


class FunnelStep(models.Model):
    """A single step / page inside a funnel."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    funnel = models.ForeignKey(FunnelConfig, on_delete=models.CASCADE, related_name='steps')
    step_order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200, blank=True)
    content = models.TextField(blank=True, help_text='Body text / HTML for this step')
    image_url = models.URLField(max_length=500, blank=True)
    button_text = models.CharField(max_length=100, blank=True, default='Next')
    button_url = models.URLField(max_length=500, blank=True, help_text='External link on last step (optional)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['step_order']

    def __str__(self):
        return f"Step {self.step_order}: {self.title}"


class FunnelSession(models.Model):
    """Tracks a visitor's progression through a funnel."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    funnel = models.ForeignKey(FunnelConfig, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=64, help_text='Browser session / cookie ID')
    current_step = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.session_key[:8]} step={self.current_step}"


# ── QR Code Access / Role (Feature 36) ────────────────
class QRCodeAccess(models.Model):
    """Grants a user a specific role on a QR code."""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        EDITOR = 'editor', 'Editor'
        VIEWER = 'viewer', 'Viewer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, related_name='access_list')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='qr_access')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='qr_grants')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('qr_code', 'user')
        ordering = ['role', 'created_at']

    def __str__(self):
        return f"{self.user} → {self.qr_code.title} ({self.role})"


# ── Bulk Upload Job ───────────────────────────────────
class BulkUploadJob(models.Model):
    """Track bulk QR creation from Excel upload."""

    class JobStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=500)
    file_url = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    result_zip_url = models.URLField(blank=True, null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
