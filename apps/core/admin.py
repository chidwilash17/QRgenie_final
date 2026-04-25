from django.contrib import admin
from .models import Organization, User, APIKey, AuditLog, Invitation


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'plan', 'is_active', 'created_at']
    list_filter = ['plan', 'is_active']
    search_fields = ['name', 'slug']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'organization', 'role', 'is_email_verified', 'last_active_at']
    list_filter = ['role', 'is_email_verified']
    search_fields = ['email', 'first_name', 'last_name']


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'prefix', 'organization', 'is_active', 'last_used_at']
    list_filter = ['is_active']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'resource_type', 'user', 'organization', 'created_at']
    list_filter = ['action', 'resource_type']
    readonly_fields = ['id', 'organization', 'user', 'action', 'resource_type', 'resource_id', 'details', 'ip_address', 'user_agent', 'created_at']


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'organization', 'role', 'accepted', 'expires_at']
    list_filter = ['accepted']
