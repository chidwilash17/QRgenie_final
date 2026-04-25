"""
Core Permissions
=================
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOrgMember(BasePermission):
    """User must belong to an organization."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.organization is not None


class IsOrgOwnerOrAdmin(BasePermission):
    """User must be org owner or admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ('owner', 'admin')


class IsOrgEditor(BasePermission):
    """User must be owner, admin, or editor."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ('owner', 'admin', 'editor')


class IsOrgViewer(BasePermission):
    """Any org member can view."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.organization is not None


class IsQROwnerOrCollaborator(BasePermission):
    """
    Object-level permission for QRCode resources.

    Read access (SAFE_METHODS):   any org member whose organization matches the QR code's org,
                                  OR any user with an explicit access entry.

    Write access (unsafe methods):
      - Org owners / admins always allowed (within their org).
      - QR creator (created_by) always allowed.
      - Users with an explicit QRCodeAccess entry with role in
        ('editor', 'admin', 'owner') are allowed.
      - Viewers (role='viewer') are read-only.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        # ── Org-level admin/owner bypass ───────────────────────────────
        if (
            obj.organization_id == getattr(user.organization, 'id', None)
            and user.role in ('owner', 'admin')
        ):
            return True

        # ── QR creator always has full access ──────────────────────────
        if obj.created_by_id == user.pk:
            return True

        # ── Explicit per-QR access entry ───────────────────────────────
        access = obj.access_list.filter(user=user).first()
        if not access:
            # Fall back to same-org read-only access for org members
            if request.method in SAFE_METHODS:
                return obj.organization_id == getattr(user.organization, 'id', None)
            return False

        if request.method in SAFE_METHODS:
            return access.role in ('viewer', 'editor', 'admin', 'owner')
        return access.role in ('editor', 'admin', 'owner')


class HasAPIKeyScope(BasePermission):
    """
    Check that the API key has the required scope(s).
    Views set required_scopes = ['qr:read'] etc.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Must be API key auth (request.auth is the APIKey instance)
        from apps.core.models import APIKey
        api_key = request.auth
        if not isinstance(api_key, APIKey):
            return False

        required = getattr(view, 'required_scopes', [])
        if not required:
            return True

        key_scopes = set(api_key.scopes or [])
        # Allow wildcard '*' scope
        if '*' in key_scopes:
            return True

        return all(s in key_scopes for s in required)
