"""
Core Models — Users, Organizations, API Keys, Audit Logs
=========================================================
"""
import uuid
import hashlib
import secrets
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ── Soft Delete Mixin ───────────────────────────────────
class SoftDeleteManager(models.Manager):
    """Default manager — hides soft-deleted rows from all ordinary queries."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteAllManager(models.Manager):
    """Unfiltered manager — includes soft-deleted rows (for admin / recovery)."""

    def get_queryset(self):
        return super().get_queryset()


class SoftDeleteMixin(models.Model):
    """
    Abstract mixin that adds soft-delete behaviour.

    Usage:
        class MyModel(SoftDeleteMixin, models.Model):
            ...

    The default `objects` manager excludes deleted rows.
    Use `all_objects` to include them (e.g. in admin / recovery views).
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteAllManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft-delete: set deleted_at instead of removing the DB row."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """Permanently remove the row from the database."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Undo a soft-delete."""
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None



class Organization(models.Model):
    """Multi-tenant organization (workspace)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    logo = models.URLField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    plan = models.CharField(max_length=50, default='free', choices=[
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('business', 'Business'),
        ('enterprise', 'Enterprise'),
    ])
    # Branding
    primary_color = models.CharField(max_length=7, default='#6366F1')
    secondary_color = models.CharField(max_length=7, default='#8B5CF6')
    # Limits
    max_qr_codes = models.IntegerField(default=50)
    max_scans_per_month = models.IntegerField(default=10000)
    max_team_members = models.IntegerField(default=3)
    max_automations = models.IntegerField(default=5)
    max_ai_tokens_per_month = models.IntegerField(default=500000)
    # Domain whitelisting — restrict destination URLs to approved domains
    allowed_domains = models.JSONField(
        default=list, blank=True,
        help_text='Allowed destination domains (e.g. ["example.com","*.example.com"]). Empty = all allowed.',
    )
    # Meta
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


# ── User ───────────────────────────────────────────────
class User(AbstractUser):
    """Custom user model with org membership and roles."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.URLField(blank=True, null=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='members',
        null=True, blank=True
    )
    role = models.CharField(max_length=30, default='member', choices=[
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
        ('member', 'Member'),
    ])
    is_email_verified = models.BooleanField(default=False)
    last_active_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── 2FA (Admin Panel) ─────────────────────────────────
    totp_secret = models.CharField(max_length=64, blank=True, default='')
    is_2fa_enabled = models.BooleanField(default=False)
    email_otp_code = models.CharField(max_length=128, blank=True, default='')
    email_otp_expires = models.DateTimeField(blank=True, null=True)

    # ── Clerk Integration ─────────────────────────────────
    clerk_id = models.CharField(max_length=255, blank=True, null=True, unique=True, db_index=True,
                                help_text='Clerk user ID for external authentication')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email


# ── API Key ────────────────────────────────────────────
class APIKey(models.Model):
    """Scoped API keys for programmatic access."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='api_keys')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)
    prefix = models.CharField(max_length=8, unique=True)
    hashed_key = models.CharField(max_length=128)
    scopes = models.JSONField(default=list, help_text='List of scopes: qr:create, qr:read, analytics:read, etc.')
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.prefix}***)"

    @staticmethod
    def generate_key():
        """Generate a new API key, return (plain_key, prefix, hashed_key)."""
        plain_key = f"qrg_{secrets.token_urlsafe(32)}"
        prefix = plain_key[:8]
        hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
        return plain_key, prefix, hashed_key

    @staticmethod
    def hash_key(plain_key: str) -> str:
        return hashlib.sha256(plain_key.encode()).hexdigest()

    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at


# ── Audit Log ──────────────────────────────────────────
class AuditLog(models.Model):
    """Immutable audit log for all critical actions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=50, db_index=True)
    resource_id = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict)
    before = models.JSONField(null=True, blank=True, help_text='Resource state before the action')
    after = models.JSONField(null=True, blank=True, help_text='Resource state after the action')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"


# ── Invitation ─────────────────────────────────────────
class Invitation(models.Model):
    """Invite team members to organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    role = models.CharField(max_length=30, default='member')
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    accepted = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['organization', 'email']

    def is_expired(self):
        return timezone.now() > self.expires_at
