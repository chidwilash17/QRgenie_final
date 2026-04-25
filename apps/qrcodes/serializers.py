"""
QR Codes Serializers
=====================
"""
import json
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
from apps.core.sanitize import sanitize_text, sanitize_rich


def _make_json_safe(data):
    """Convert DRF serializer output to JSON-safe dict (handles UUID, datetime, etc.)."""
    return json.loads(JSONRenderer().render(data))
from .models import (
    QRCode, QRVersion, RoutingRule, MultiLinkItem,
    FileAttachment, PaymentConfig, ChatConfig, BulkUploadJob, RotationSchedule,
    LanguageRoute, TimeSchedule, PDFDocument, VideoDocument, DeviceRoute,
    GeoFenceRule, ABTest, DeepLink, TokenRedirect, QRExpiry, ScanAlert,
    LoyaltyProgram, LoyaltyMember, DigitalVCard,
    ProductAuth, ProductSerial,
    DocumentUploadForm, DocumentSubmission, DocumentFile,
    FunnelConfig, FunnelStep, FunnelSession,
    QRCodeAccess,
)


# ── Routing Rule ──────────────────────────────────────
class RoutingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoutingRule
        fields = [
            'id', 'rule_type', 'priority', 'is_active',
            'conditions', 'destination_url', 'label',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── Multi-Link ────────────────────────────────────────
class MultiLinkItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultiLinkItem
        fields = [
            'id', 'title', 'url', 'icon', 'thumbnail_url',
            'sort_order', 'click_count', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'click_count', 'created_at']


# ── File Attachment ───────────────────────────────────
class FileAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = [
            'id', 'file_name', 'file_url', 'file_size', 'mime_type',
            'version', 'is_current', 'download_count', 'created_at',
        ]
        read_only_fields = ['id', 'download_count', 'created_at']


# ── Payment Config ────────────────────────────────────
class PaymentConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentConfig
        fields = [
            'id', 'gateway', 'amount', 'currency',
            'upi_id', 'payment_link', 'merchant_name', 'description',
        ]
        read_only_fields = ['id']


# ── Chat Config ──────────────────────────────────────
class ChatConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatConfig
        fields = [
            'id', 'whatsapp_number', 'whatsapp_message',
            'telegram_username', 'messenger_page_id',
        ]
        read_only_fields = ['id']


# ── QR Version ────────────────────────────────────────
class QRVersionSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.CharField(source='changed_by.email', read_only=True, default=None)

    class Meta:
        model = QRVersion
        fields = [
            'id', 'version_number', 'snapshot',
            'changed_by', 'changed_by_email', 'change_summary', 'created_at',
        ]


# ── QR Code (List) ────────────────────────────────────
class QRCodeListSerializer(serializers.ModelSerializer):
    short_url = serializers.ReadOnlyField()
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default=None)
    rules_count = serializers.SerializerMethodField()
    landing_page = serializers.SerializerMethodField()

    class Meta:
        model = QRCode
        fields = [
            'id', 'title', 'slug', 'description', 'qr_type', 'status',
            'destination_url', 'short_url', 'qr_image_url',
            'is_dynamic', 'foreground_color', 'background_color',
            'module_style', 'frame_style',
            'is_password_protected', 'expires_at', 'scan_limit',
            'total_scans', 'unique_scans', 'tags', 'folder',
            'utm_source', 'utm_medium', 'utm_campaign',
            'animation_glow', 'glow_color', 'glow_intensity', 'gif_background_url',
            'current_version', 'is_frozen', 'frozen_by', 'frozen_at',
            'rules_count', 'landing_page',
            'logo_url', 'fallback_url', 'error_correction',
            'created_by', 'created_by_email',
            'created_at', 'updated_at',
        ]

    def get_rules_count(self, obj):
        return obj.rules.filter(is_active=True).count()

    def get_landing_page(self, obj):
        try:
            lp = obj.landing_pages.first()
        except Exception:
            return None
        if not lp:
            return None
        from django.conf import settings
        base = getattr(settings, 'SITE_BASE_URL', 'http://localhost:8000')
        cfg = lp.page_config or {}
        return {
            'id': str(lp.id),
            'title': lp.title,
            'slug': lp.slug,
            'is_published': lp.is_published,
            'public_url': f"{base}/p/{lp.slug}/",
            'page_type': cfg.get('page_type', ''),
            'form_data': cfg.get('form_data', {}),
            'page_config': cfg,
        }


# ── QR Code (Detail) ─────────────────────────────────
class QRCodeDetailSerializer(serializers.ModelSerializer):
    short_url = serializers.ReadOnlyField()
    rules = RoutingRuleSerializer(many=True, read_only=True)
    multi_links = MultiLinkItemSerializer(many=True, read_only=True)
    files = FileAttachmentSerializer(many=True, read_only=True)
    payment_config = PaymentConfigSerializer(read_only=True)
    chat_config = ChatConfigSerializer(read_only=True)
    versions = QRVersionSerializer(many=True, read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default=None)
    landing_page = serializers.SerializerMethodField()

    def get_landing_page(self, obj):
        """Return essential landing page data if a landing page is linked."""
        try:
            lp = obj.landing_pages.select_related().first()
        except Exception:
            return None
        if not lp:
            return None
        from django.conf import settings
        base = getattr(settings, 'SITE_BASE_URL', 'http://localhost:8000')
        cfg = lp.page_config or {}
        return {
            'id': str(lp.id),
            'title': lp.title,
            'slug': lp.slug,
            'is_published': lp.is_published,
            'public_url': f"{base}/p/{lp.slug}/",
            'page_type': cfg.get('page_type', ''),
            'form_data': cfg.get('form_data', {}),
            'page_config': cfg,
        }

    class Meta:
        model = QRCode
        fields = [
            'id', 'title', 'slug', 'description', 'qr_type', 'status',
            'destination_url', 'fallback_url', 'short_url', 'qr_image_url',
            'is_dynamic', 'static_content',
            'foreground_color', 'background_color', 'logo_url', 'error_correction',
            'module_style', 'gradient_type', 'gradient_start_color', 'gradient_end_color',
            'frame_style', 'frame_color', 'frame_text', 'frame_text_color',
            'is_password_protected', 'expires_at', 'scan_limit',
            'total_scans', 'unique_scans', 'tags', 'metadata', 'folder',
            'utm_source', 'utm_medium', 'utm_campaign',
            'animation_glow', 'glow_color', 'glow_intensity', 'gif_background_url',
            'current_version', 'is_frozen', 'frozen_by', 'frozen_at',
            'rules', 'multi_links', 'files',
            'payment_config', 'chat_config', 'versions', 'landing_page',
            'created_by', 'created_by_email',
            'created_at', 'updated_at',
        ]


# ── QR Code (Create / Update) ────────────────────────
class QRCodeCreateSerializer(serializers.ModelSerializer):
    # Nested writable for type-specific data
    multi_links = MultiLinkItemSerializer(many=True, required=False)
    payment_config = PaymentConfigSerializer(required=False)
    chat_config = ChatConfigSerializer(required=False)
    rules = RoutingRuleSerializer(many=True, required=False)

    class Meta:
        model = QRCode
        fields = [
            'title', 'description', 'qr_type', 'destination_url', 'fallback_url',
            'is_dynamic', 'static_content',
            'foreground_color', 'background_color', 'logo_url', 'error_correction',
            'module_style', 'gradient_type', 'gradient_start_color', 'gradient_end_color',
            'frame_style', 'frame_color', 'frame_text', 'frame_text_color',
            'is_password_protected', 'expires_at', 'scan_limit',
            'tags', 'metadata', 'folder',
            'utm_source', 'utm_medium', 'utm_campaign',
            'animation_glow', 'glow_color', 'glow_intensity', 'gif_background_url',
            'multi_links', 'payment_config', 'chat_config', 'rules',
        ]

    def validate_title(self, value):
        """Strip all HTML from QR code titles."""
        return sanitize_text(value)

    def validate_description(self, value):
        """Allow minimal rich text in descriptions but strip dangerous tags."""
        return sanitize_rich(value)

    def validate_destination_url(self, value):
        """Enforce organization domain whitelist on destination URLs."""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            org = getattr(request.user, 'organization', None)
            if org and org.allowed_domains:
                from apps.core.utils import validate_domain_whitelist
                if not validate_domain_whitelist(value, org.allowed_domains):
                    raise serializers.ValidationError(
                        f'Domain not in organization whitelist. Allowed: {", ".join(org.allowed_domains)}'
                    )
        return value

    def validate_fallback_url(self, value):
        """Enforce organization domain whitelist on fallback URLs."""
        if not value:
            return value
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            org = getattr(request.user, 'organization', None)
            if org and org.allowed_domains:
                from apps.core.utils import validate_domain_whitelist
                if not validate_domain_whitelist(value, org.allowed_domains):
                    raise serializers.ValidationError(
                        f'Domain not in organization whitelist. Allowed: {", ".join(org.allowed_domains)}'
                    )
        return value

    def create(self, validated_data):
        multi_links_data = validated_data.pop('multi_links', [])
        payment_data = validated_data.pop('payment_config', None)
        chat_data = validated_data.pop('chat_config', None)
        rules_data = validated_data.pop('rules', [])

        # Handle password
        password = self.context.get('password')
        if password and validated_data.get('is_password_protected'):
            import bcrypt
            validated_data['password_hash'] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        qr = QRCode.objects.create(**validated_data)

        # Auto-populate UTM params if left blank (Feature 42)
        utm_changed = False
        if not qr.utm_source:
            qr.utm_source = 'qrgenie'
            utm_changed = True
        if not qr.utm_medium:
            qr.utm_medium = 'qr_code'
            utm_changed = True
        if not qr.utm_campaign:
            qr.utm_campaign = qr.slug
            utm_changed = True
        if utm_changed:
            qr.save(update_fields=['utm_source', 'utm_medium', 'utm_campaign'])

        # Create nested objects
        for link_data in multi_links_data:
            MultiLinkItem.objects.create(qr_code=qr, **link_data)

        if payment_data:
            PaymentConfig.objects.create(qr_code=qr, **payment_data)

        if chat_data:
            ChatConfig.objects.create(qr_code=qr, **chat_data)

        for rule_data in rules_data:
            RoutingRule.objects.create(qr_code=qr, **rule_data)

        # Create initial version
        QRVersion.objects.create(
            qr_code=qr,
            version_number=1,
            snapshot=_make_json_safe(QRCodeDetailSerializer(qr).data),
            changed_by=qr.created_by,
            change_summary='Initial creation',
        )

        return qr

    def update(self, instance, validated_data):
        validated_data.pop('multi_links', None)
        validated_data.pop('payment_config', None)
        validated_data.pop('chat_config', None)
        validated_data.pop('rules', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


# ── Rotation Schedule ────────────────────────────────
class RotationScheduleSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a RotationSchedule.

    `pages` is a free-form JSON list whose shape depends on rotation_type:
      daily:  [{"page_url":"...", "label":"Page A"}, ...]
      weekly: [{"page_url":"...", "label":"Mon", "day_of_week":0}, ...]
      custom: [{"page_url":"...", "label":"Campaign", "start_date":"YYYY-MM-DD", "end_date":"YYYY-MM-DD"}, ...]
    """
    class Meta:
        model = RotationSchedule
        fields = [
            'id', 'is_active', 'rotation_type', 'tz', 'pages',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_pages(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('pages must be a JSON array.')
        for i, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f'pages[{i}] must be an object.')
            if not entry.get('page_url'):
                raise serializers.ValidationError(f'pages[{i}] is missing required field \'page_url\'.')
        return value


# ── Language Route (Feature 8) ────────────────────────
class LanguageRouteSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a LanguageRoute.

    `routes` shape: [{"lang":"en","url":"https://…","label":"English"}, ...]
    `geo_fallback` shape: {"IN":"hi","DE":"de","JP":"ja"}
    """
    class Meta:
        model = LanguageRoute
        fields = [
            'id', 'is_active', 'routes', 'default_url',
            'geo_fallback', 'geo_direct', 'use_quality_weights',
            'mandatory_location',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_routes(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('routes must be a JSON array.')
        for i, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f'routes[{i}] must be an object.')
            if not entry.get('lang'):
                raise serializers.ValidationError(f'routes[{i}] is missing required field \'lang\'.')
            if not entry.get('url'):
                raise serializers.ValidationError(f'routes[{i}] is missing required field \'url\'.')
            url = entry['url']
            if not url.startswith(('http://', 'https://')):
                raise serializers.ValidationError(f'routes[{i}].url must start with http:// or https://.')
        return value

    def validate_geo_fallback(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('geo_fallback must be a JSON object.')
        for key, val in value.items():
            if not isinstance(key, str) or not (2 <= len(key) <= 5):
                raise serializers.ValidationError(
                    f'geo_fallback key "{key}" must be a 2-letter country code '
                    f'or region code like "IN-AP" (2–5 chars).'
                )
            if not isinstance(val, str) or not val:
                raise serializers.ValidationError(f'geo_fallback["{key}"] must be a non-empty language code.')
        return value

    def validate_geo_direct(self, value):
        """Validate direct geo→URL mappings (district/city level)."""
        if not isinstance(value, list):
            raise serializers.ValidationError('geo_direct must be a JSON array.')
        for i, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f'geo_direct[{i}] must be an object.')
            if not entry.get('country'):
                raise serializers.ValidationError(f'geo_direct[{i}] is missing required field "country".')
            if not entry.get('state'):
                raise serializers.ValidationError(f'geo_direct[{i}] is missing required field "state".')
            if not entry.get('url'):
                raise serializers.ValidationError(f'geo_direct[{i}] is missing required field "url".')
            url = entry['url']
            if not url.startswith(('http://', 'https://')):
                raise serializers.ValidationError(f'geo_direct[{i}].url must start with http:// or https://.')
            # district is optional
        return value


# ── Time Schedule (Feature 9) ─────────────────────────
class TimeScheduleSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a TimeSchedule.

    `rules` shape: [
      {
        "label": "Breakfast",
        "url": "https://example.com/breakfast",
        "start_time": "06:00",
        "end_time": "11:00",
        "days": ["mon","tue","wed","thu","fri"]   // optional, all days if empty
      }
    ]
    """
    class Meta:
        model = TimeSchedule
        fields = [
            'id', 'is_active', 'tz', 'rules', 'default_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    VALID_DAYS = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}

    def validate_rules(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('rules must be a JSON array.')
        for i, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f'rules[{i}] must be an object.')
            if not entry.get('url'):
                raise serializers.ValidationError(f'rules[{i}] is missing required field "url".')
            url = entry['url']
            if not url.startswith(('http://', 'https://')):
                raise serializers.ValidationError(f'rules[{i}].url must start with http:// or https://.')
            if not entry.get('start_time'):
                raise serializers.ValidationError(f'rules[{i}] is missing required field "start_time".')
            if not entry.get('end_time'):
                raise serializers.ValidationError(f'rules[{i}] is missing required field "end_time".')
            # Validate time format HH:MM
            import re
            for field in ('start_time', 'end_time'):
                val = entry.get(field, '')
                if not re.match(r'^\d{2}:\d{2}$', val):
                    raise serializers.ValidationError(
                        f'rules[{i}].{field} must be in HH:MM format (got "{val}").'
                    )
            # Validate days if provided
            days = entry.get('days', [])
            if days:
                if not isinstance(days, list):
                    raise serializers.ValidationError(f'rules[{i}].days must be an array.')
                for d in days:
                    if d.lower() not in self.VALID_DAYS:
                        raise serializers.ValidationError(
                            f'rules[{i}].days contains invalid day "{d}". '
                            f'Must be one of: {sorted(self.VALID_DAYS)}'
                        )
        return value


# ── PDF Document (Feature 11) ─────────────────────────
class PDFDocumentSerializer(serializers.ModelSerializer):
    viewer_url = serializers.ReadOnlyField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = PDFDocument
        fields = [
            'id', 'original_filename', 'file_size', 'file_size_display',
            'mime_type', 'page_count', 'is_active', 'allow_download',
            'title', 'access_token', 'viewer_url', 'view_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'original_filename', 'file_size', 'file_size_display',
            'mime_type', 'page_count', 'access_token', 'viewer_url',
            'view_count', 'created_at', 'updated_at',
        ]

    def get_file_size_display(self, obj):
        size = obj.file_size or 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


# ── Video Document (Feature 13) ────────────────────────
class VideoDocumentSerializer(serializers.ModelSerializer):
    player_url = serializers.ReadOnlyField()
    file_size_display = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = VideoDocument
        fields = [
            'id', 'original_filename', 'file_size', 'file_size_display',
            'mime_type', 'duration_seconds', 'duration_display',
            'is_active', 'allow_download', 'autoplay', 'loop',
            'title', 'access_token', 'player_url', 'view_count',
            'thumbnail_path', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'original_filename', 'file_size', 'file_size_display',
            'mime_type', 'duration_seconds', 'duration_display',
            'access_token', 'player_url', 'view_count',
            'thumbnail_path', 'created_at', 'updated_at',
        ]

    def get_file_size_display(self, obj):
        size = obj.file_size or 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def get_duration_display(self, obj):
        secs = int(obj.duration_seconds or 0)
        if secs <= 0:
            return 'Unknown'
        mins, s = divmod(secs, 60)
        hrs, mins = divmod(mins, 60)
        if hrs:
            return f"{hrs}:{mins:02d}:{s:02d}"
        return f"{mins}:{s:02d}"


# ── Device Route (Feature 15) ─────────────────────────
class DeviceRouteSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a DeviceRoute.
    Simple flat structure — one URL per platform.
    """
    class Meta:
        model = DeviceRoute
        fields = [
            'id', 'is_active',
            'android_url', 'ios_url', 'windows_url', 'mac_url',
            'linux_url', 'tablet_url', 'default_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── Geo-Fence Rule (Feature 17) ───────────────────────
class GeoFenceRuleSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a GeoFenceRule.
    zones: list of {label, lat, lng, radius_meters, url}
    """
    class Meta:
        model = GeoFenceRule
        fields = [
            'id', 'is_active', 'zones', 'default_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── A/B Split Test (Feature 18) ────────────────────────
class ABTestSerializer(serializers.ModelSerializer):
    """
    Serialize / validate an ABTest.
    variants: list of {label, url, weight}
    """
    class Meta:
        model = ABTest
        fields = [
            'id', 'is_active', 'variants',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── App Deep Link (Feature 19) ─────────────────────────
class DeepLinkSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a DeepLink.
    Flat structure — one deep link / fallback per platform.
    """
    class Meta:
        model = DeepLink
        fields = [
            'id', 'is_active',
            'ios_deep_link', 'ios_fallback_url',
            'android_deep_link', 'android_fallback_url',
            'custom_uri', 'fallback_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ── Short-Lived Token Redirect (Feature 20) ────────────
class TokenRedirectSerializer(serializers.ModelSerializer):
    """
    Serialize / validate a TokenRedirect.
    Modes: timed | single_use | limited_sessions.
    """
    class Meta:
        model = TokenRedirect
        fields = [
            'id', 'is_active', 'mode',
            'ttl_seconds', 'max_uses',
            'first_used_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'first_used_at', 'created_at', 'updated_at']

    def validate_ttl_seconds(self, value):
        if value < 10:
            raise serializers.ValidationError('TTL must be at least 10 seconds.')
        if value > 86400:
            raise serializers.ValidationError('TTL cannot exceed 86400 seconds (24 hours).')
        return value

    def validate_max_uses(self, value):
        if value < 1:
            raise serializers.ValidationError('Max uses must be at least 1.')
        if value > 10000:
            raise serializers.ValidationError('Max uses cannot exceed 10000.')
        return value

    def save(self, **kwargs):
        """
        On every save, reset first_used_at and clear old usage records
        so the QR gets a fresh start with the new/updated config.
        """
        instance = super().save(**kwargs)
        # Reset first-use timestamp so the timer restarts
        if instance.first_used_at is not None:
            instance.first_used_at = None
            instance.save(update_fields=['first_used_at'])
        # Clear all previous usage records
        instance.usages.all().delete()
        return instance


# ── Expiry-Based QR (Feature 21) ─────────────────────
class QRExpirySerializer(serializers.ModelSerializer):
    """
    Serialize / validate a QRExpiry.
    Modes: date | datetime | scan_count.
    """
    class Meta:
        model = QRExpiry
        fields = [
            'id', 'is_active', 'expiry_type',
            'expiry_date', 'expiry_datetime',
            'max_scans', 'scan_count',
            'expired_redirect_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'scan_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        expiry_type = attrs.get('expiry_type', getattr(self.instance, 'expiry_type', 'date'))
        if expiry_type == 'date' and not attrs.get('expiry_date') and not getattr(self.instance, 'expiry_date', None):
            raise serializers.ValidationError({'expiry_date': 'Required for date-based expiry.'})
        if expiry_type == 'datetime' and not attrs.get('expiry_datetime') and not getattr(self.instance, 'expiry_datetime', None):
            raise serializers.ValidationError({'expiry_datetime': 'Required for datetime-based expiry.'})
        if expiry_type == 'scan_count':
            max_scans = attrs.get('max_scans', getattr(self.instance, 'max_scans', 100))
            if max_scans < 1:
                raise serializers.ValidationError({'max_scans': 'Must be at least 1.'})
        return attrs

    def save(self, **kwargs):
        """Reset scan_count when config is saved (fresh start)."""
        instance = super().save(**kwargs)
        if instance.scan_count > 0:
            instance.scan_count = 0
            instance.save(update_fields=['scan_count'])
        return instance


# ── Scan Alerts (Feature 25) ──────────────────────────
class ScanAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanAlert
        fields = [
            'id', 'is_active', 'alert_events', 'email_recipients',
            'milestone_every', 'spike_window_minutes', 'spike_threshold',
            'cooldown_minutes', 'last_notified_at', 'total_alerts_sent',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_notified_at', 'total_alerts_sent', 'created_at', 'updated_at']

    VALID_EVENTS = {'every_scan', 'milestone', 'first_scan', 'scan_spike'}

    def validate_alert_events(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a list of event types.')
        for ev in value:
            if ev not in self.VALID_EVENTS:
                raise serializers.ValidationError(f'Invalid event type: {ev}')
        return value

    def validate_email_recipients(self, value):
        if not value or not value.strip():
            return value
        import re
        emails = [e.strip() for e in value.split(',') if e.strip()]
        email_re = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
        for email in emails:
            if not email_re.match(email):
                raise serializers.ValidationError(f'Invalid email: {email}')
        return ', '.join(emails)


# ── Loyalty Point QR (Feature 26) ─────────────────────
class LoyaltyMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyMember
        fields = ['id', 'identifier', 'name', 'points', 'total_scans', 'last_scan_at', 'created_at']
        read_only_fields = ['id', 'points', 'total_scans', 'last_scan_at', 'created_at']


class LoyaltyProgramSerializer(serializers.ModelSerializer):
    members = LoyaltyMemberSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = LoyaltyProgram
        fields = [
            'id', 'is_active', 'program_name', 'points_per_scan',
            'max_points_per_day', 'bonus_points', 'reward_tiers',
            'total_members', 'total_points_issued',
            'members', 'member_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_members', 'total_points_issued', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()

    def validate_reward_tiers(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a list of reward tiers.')
        for tier in value:
            if not isinstance(tier, dict):
                raise serializers.ValidationError('Each tier must be an object.')
            if 'name' not in tier or 'points_required' not in tier:
                raise serializers.ValidationError('Each tier needs name and points_required.')
        return value


# ── Digital vCard (Feature 28) ────────────────────────
class DigitalVCardSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = DigitalVCard
        fields = [
            'id', 'is_active',
            'first_name', 'last_name', 'prefix', 'suffix', 'full_name',
            'organization', 'title', 'department',
            'email', 'email_work', 'phone', 'phone_work', 'phone_cell',
            'website', 'linkedin', 'twitter', 'github', 'instagram',
            'street', 'city', 'state', 'zip_code', 'country',
            'photo_url', 'accent_color', 'bio', 'note',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'full_name', 'created_at', 'updated_at']
        extra_kwargs = {
            'first_name': {'allow_blank': True},
            'email': {'allow_blank': True},
            'email_work': {'allow_blank': True},
            'website': {'allow_blank': True},
            'linkedin': {'allow_blank': True},
            'github': {'allow_blank': True},
            'photo_url': {'allow_blank': True},
        }

    def get_full_name(self, obj):
        return obj.full_name()

    def validate_first_name(self, value):
        return sanitize_text(value)

    def validate_last_name(self, value):
        return sanitize_text(value)

    def validate_organization(self, value):
        return sanitize_text(value)

    def validate_title(self, value):
        return sanitize_text(value)

    def validate_bio(self, value):
        return sanitize_rich(value)

    def validate_note(self, value):
        return sanitize_text(value)


# ── Product Authentication (Feature 31) ───────────────
class ProductSerialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSerial
        fields = [
            'id', 'serial_number', 'hmac_signature', 'status',
            'batch_label', 'manufactured_date',
            'total_scans', 'first_scanned_at', 'last_scanned_at',
            'last_scanned_ip', 'last_scanned_location', 'created_at',
        ]
        read_only_fields = [
            'id', 'hmac_signature', 'total_scans',
            'first_scanned_at', 'last_scanned_at',
            'last_scanned_ip', 'last_scanned_location', 'created_at',
        ]


class ProductAuthSerializer(serializers.ModelSerializer):
    serial_count = serializers.SerializerMethodField()
    verified_count = serializers.SerializerMethodField()
    unscanned_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductAuth
        fields = [
            'id', 'is_active',
            'product_name', 'manufacturer', 'description', 'product_image_url',
            'secret_key', 'brand_color', 'support_url', 'support_email',
            'serial_count', 'verified_count', 'unscanned_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'serial_count', 'verified_count', 'unscanned_count', 'created_at', 'updated_at']
        extra_kwargs = {
            'secret_key': {'write_only': True, 'required': False},
            'product_name': {'allow_blank': True, 'required': False},
            'manufacturer': {'allow_blank': True, 'required': False},
            'description': {'allow_blank': True, 'required': False},
            'product_image_url': {'allow_blank': True, 'required': False, 'validators': []},
            'support_url': {'allow_blank': True, 'required': False, 'validators': []},
            'support_email': {'allow_blank': True, 'required': False},
            'brand_color': {'required': False},
        }

    def get_serial_count(self, obj):
        return obj.serials.count()

    def get_verified_count(self, obj):
        return obj.serials.filter(status='verified').count()

    def get_unscanned_count(self, obj):
        total = obj.serials.count()
        verified = obj.serials.filter(status='verified').count()
        return total - verified  # always an int, never null/NaN


# ── Document Upload Form (Feature 33) ─────────────────
class DocumentFileSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentFile
        fields = [
            'id', 'original_name', 'file_path', 'file_size',
            'mime_type', 'category', 'download_url', 'created_at',
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        return f'/media/{obj.file_path}'


class DocumentSubmissionSerializer(serializers.ModelSerializer):
    files = DocumentFileSerializer(many=True, read_only=True)
    file_count = serializers.SerializerMethodField()

    class Meta:
        model = DocumentSubmission
        fields = [
            'id', 'submitter_name', 'submitter_email', 'submitter_phone',
            'ip_address', 'user_agent', 'notes', 'file_count', 'files', 'created_at',
        ]
        read_only_fields = fields

    def get_file_count(self, obj):
        return obj.files.count()


class DocumentUploadFormSerializer(serializers.ModelSerializer):
    submission_count = serializers.SerializerMethodField()
    total_files = serializers.SerializerMethodField()

    class Meta:
        model = DocumentUploadForm
        fields = [
            'id', 'is_active', 'title', 'description',
            'allowed_types', 'allowed_extensions',
            'max_file_size_mb', 'max_files',
            'require_name', 'require_email', 'require_phone',
            'success_message', 'brand_color', 'notify_email',
            'submission_count', 'total_files',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'submission_count', 'total_files', 'created_at', 'updated_at']
        extra_kwargs = {
            'title': {'allow_blank': True, 'required': False},
            'description': {'allow_blank': True, 'required': False},
            'allowed_extensions': {'allow_blank': True, 'required': False},
            'success_message': {'allow_blank': True, 'required': False},
            'notify_email': {'allow_blank': True, 'required': False},
        }

    def get_submission_count(self, obj):
        return obj.submissions.count()

    def get_total_files(self, obj):
        return DocumentFile.objects.filter(submission__form=obj).count()


# ── Funnel (Feature 34) ───────────────────────────────
class FunnelStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunnelStep
        fields = [
            'id', 'funnel', 'step_order', 'title', 'content',
            'image_url', 'button_text', 'button_url', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'funnel': {'required': False},
            'title': {'required': False, 'allow_blank': True},
            'content': {'required': False, 'allow_blank': True},
            'image_url': {'required': False, 'allow_blank': True, 'validators': []},
            'button_text': {'required': False, 'allow_blank': True},
            'button_url': {'required': False, 'allow_blank': True, 'validators': []},
        }


class FunnelConfigSerializer(serializers.ModelSerializer):
    steps = FunnelStepSerializer(many=True, read_only=True)
    step_count = serializers.SerializerMethodField()
    session_count = serializers.SerializerMethodField()
    completion_count = serializers.SerializerMethodField()

    class Meta:
        model = FunnelConfig
        fields = [
            'id', 'qr_code', 'is_active', 'title', 'description',
            'brand_color', 'show_progress_bar', 'allow_back_navigation',
            'steps', 'step_count', 'session_count', 'completion_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'qr_code': {'required': False},
            'title': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True},
            'brand_color': {'required': False, 'allow_blank': True},
        }

    def get_step_count(self, obj):
        return obj.steps.count()

    def get_session_count(self, obj):
        return obj.sessions.count()

    def get_completion_count(self, obj):
        return obj.sessions.filter(is_completed=True).count()


class FunnelSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunnelSession
        fields = [
            'id', 'funnel', 'session_key', 'current_step',
            'is_completed', 'ip_address', 'user_agent',
            'started_at', 'completed_at',
        ]
        read_only_fields = ['id', 'started_at']


# ── QR Code Access / Role (Feature 36) ────────────────
class QRCodeAccessSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    granted_by_email = serializers.EmailField(source='granted_by.email', read_only=True, default=None)

    class Meta:
        model = QRCodeAccess
        fields = [
            'id', 'qr_code', 'user', 'user_email', 'user_name',
            'role', 'granted_by', 'granted_by_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'qr_code': {'required': False},
            'user': {'required': False},
            'granted_by': {'required': False},
        }

    def get_user_name(self, obj):
        u = obj.user
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.email


# ── Bulk Upload ───────────────────────────────────────
class BulkUploadJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkUploadJob
        fields = [
            'id', 'file_name', 'status', 'total_rows',
            'processed_rows', 'success_count', 'error_count',
            'errors', 'result_zip_url',
            'started_at', 'completed_at', 'created_at',
        ]
