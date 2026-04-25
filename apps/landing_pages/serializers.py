from rest_framework import serializers
from .models import LandingPage, LandingPageTemplate, Popup, PopupSubmission


class LandingPageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandingPageTemplate
        fields = [
            'id', 'name', 'category', 'description', 'thumbnail_url',
            'html_template', 'css', 'default_config', 'is_premium', 'created_at',
        ]


class LandingPageListSerializer(serializers.ModelSerializer):
    qr_code_slug = serializers.CharField(source='qr_code.slug', read_only=True, default=None)
    template_name = serializers.CharField(source='template.name', read_only=True, default=None)
    public_url = serializers.SerializerMethodField()
    page_type = serializers.SerializerMethodField()
    form_data = serializers.SerializerMethodField()

    class Meta:
        model = LandingPage
        fields = [
            'id', 'title', 'slug', 'qr_code', 'qr_code_slug',
            'template', 'template_name', 'is_ai_generated', 'is_published',
            'view_count', 'public_url', 'page_type', 'form_data',
            'page_config', 'created_at', 'updated_at',
        ]

    def get_page_type(self, obj):
        return (obj.page_config or {}).get('page_type', '')

    def get_form_data(self, obj):
        return (obj.page_config or {}).get('form_data', {})

    def get_public_url(self, obj):
        from django.conf import settings
        base = getattr(settings, 'QR_BASE_REDIRECT_URL', 'http://localhost:8000')
        return f"{base}/p/{obj.slug}/"


class LandingPageDetailSerializer(serializers.ModelSerializer):
    qr_code_slug = serializers.CharField(source='qr_code.slug', read_only=True, default=None)
    public_url = serializers.SerializerMethodField()

    class Meta:
        model = LandingPage
        fields = [
            'id', 'title', 'slug', 'meta_description', 'favicon_url',
            'qr_code', 'qr_code_slug', 'template',
            'html_content', 'custom_css', 'custom_js', 'page_config',
            'show_qrgenie_badge', 'custom_domain',
            'is_ai_generated', 'ai_prompt', 'is_published',
            'view_count', 'public_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'view_count', 'created_at', 'updated_at']

    def get_public_url(self, obj):
        from django.conf import settings
        base = getattr(settings, 'QR_BASE_REDIRECT_URL', 'http://localhost:8000')
        return f"{base}/p/{obj.slug}/"


class LandingPageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandingPage
        fields = [
            'title', 'slug', 'meta_description', 'favicon_url',
            'qr_code', 'template', 'html_content', 'custom_css', 'custom_js',
            'page_config', 'show_qrgenie_badge', 'custom_domain',
            'is_published',
        ]

    def create(self, validated_data):
        request = self.context['request']
        return LandingPage.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )


# ── Popup Serializers (Feature 14) ──────────────────────────────────────────


class PopupListSerializer(serializers.ModelSerializer):
    popup_type_display = serializers.CharField(source='get_popup_type_display', read_only=True)
    trigger_display = serializers.CharField(source='get_trigger_display', read_only=True)
    position_display = serializers.CharField(source='get_position_display', read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Popup
        fields = [
            'id', 'name', 'popup_type', 'popup_type_display',
            'trigger', 'trigger_display', 'position', 'position_display',
            'is_active', 'is_published',
            'view_count', 'click_count', 'submit_count', 'conversion_rate',
            'embed_token',
            'created_at', 'updated_at',
        ]


class PopupDetailSerializer(serializers.ModelSerializer):
    popup_type_display = serializers.CharField(source='get_popup_type_display', read_only=True)
    trigger_display = serializers.CharField(source='get_trigger_display', read_only=True)
    position_display = serializers.CharField(source='get_position_display', read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)
    embed_url = serializers.CharField(read_only=True)

    class Meta:
        model = Popup
        fields = [
            'id', 'name', 'popup_type', 'popup_type_display',
            'trigger', 'trigger_display', 'trigger_value',
            'position', 'position_display',
            'show_overlay', 'allow_close', 'show_once', 'frequency_hours',
            'content', 'style',
            'landing_page',
            'is_active', 'is_published',
            'view_count', 'click_count', 'submit_count', 'conversion_rate',
            'embed_token', 'embed_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'view_count', 'click_count', 'submit_count',
            'embed_token', 'created_at', 'updated_at',
        ]


class PopupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Popup
        fields = [
            'name', 'popup_type',
            'trigger', 'trigger_value', 'position',
            'show_overlay', 'allow_close', 'show_once', 'frequency_hours',
            'content', 'style',
            'landing_page', 'is_active', 'is_published',
        ]

    def create(self, validated_data):
        request = self.context['request']
        return Popup.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )


class PopupSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PopupSubmission
        fields = ['id', 'popup', 'data', 'page_url', 'created_at']
        read_only_fields = ['id', 'created_at']
