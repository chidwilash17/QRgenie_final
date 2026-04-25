"""
Core Serializers — Auth, Users, Organizations
===============================================
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from datetime import timedelta
from .models import Organization, APIKey, AuditLog, Invitation

User = get_user_model()


# ── JWT Token ──────────────────────────────────────────
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT with extra claims."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        if user.organization:
            token['org_id'] = str(user.organization.id)
            token['org_slug'] = user.organization.slug
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        # Update last active
        self.user.last_active_at = timezone.now()
        self.user.save(update_fields=['last_active_at'])
        return data


# ── User ───────────────────────────────────────────────
class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    organization_name = serializers.CharField(source='organization.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'full_name', 'phone', 'avatar', 'role',
            'organization', 'organization_name',
            'is_email_verified', 'last_active_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_email_verified']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    organization_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'organization_name']

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        org_name = validated_data.pop('organization_name', None)
        password = validated_data.pop('password')

        # Auto-generate username from email
        email = validated_data.get('email', '')
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        validated_data['username'] = username

        user = User(**validated_data)
        user.set_password(password)

        if org_name:
            from django.utils.text import slugify
            slug = slugify(org_name)
            # Ensure unique slug
            base_slug = slug
            counter = 1
            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            org = Organization.objects.create(name=org_name, slug=slug)
            user.organization = org
            user.role = 'owner'
        else:
            # Auto-create a personal organization so the user isn't locked out
            from django.utils.text import slugify
            personal_name = f"{email.split('@')[0]}'s Workspace"
            slug = slugify(personal_name)
            base_slug = slug
            counter = 1
            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            org = Organization.objects.create(name=personal_name, slug=slug)
            user.organization = org
            user.role = 'owner'

        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'avatar']


# ── Organization ───────────────────────────────────────
class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'logo', 'website', 'plan',
            'primary_color', 'secondary_color',
            'max_qr_codes', 'max_scans_per_month', 'max_team_members',
            'max_automations', 'max_ai_tokens_per_month',
            'is_active', 'member_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'plan', 'is_active', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['name', 'logo', 'website', 'primary_color', 'secondary_color']


# ── API Key ────────────────────────────────────────────
class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ['id', 'name', 'prefix', 'scopes', 'last_used_at', 'expires_at', 'is_active', 'created_at']
        read_only_fields = ['id', 'prefix', 'last_used_at', 'created_at']


class APIKeyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ['name', 'scopes', 'expires_at']


# ── Audit Log ──────────────────────────────────────────
class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True, default='System')

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_email', 'action',
            'resource_type', 'resource_id', 'details',
            'ip_address', 'created_at',
        ]


# ── Invitation ─────────────────────────────────────────
class InvitationSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.CharField(source='invited_by.email', read_only=True)

    class Meta:
        model = Invitation
        fields = ['id', 'email', 'role', 'invited_by_email', 'accepted', 'expires_at', 'created_at']
        read_only_fields = ['id', 'invited_by_email', 'accepted', 'created_at']


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=['admin', 'editor', 'viewer', 'member'], default='member')
