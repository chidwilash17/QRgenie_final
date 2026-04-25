"""
API Key Authentication Backend
================================
Authenticates requests using X-API-Key header.
Attaches a virtual user object scoped to the API key's organization.
"""
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import APIKey


class APIKeyUser:
    """Lightweight user-like object for API key authenticated requests."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.organization = api_key.organization
        self.id = api_key.created_by_id
        self.pk = self.id
        self.email = f"api-key:{api_key.prefix}"
        self.role = 'api'
        self.is_authenticated = True
        self.is_anonymous = False
        self.is_active = True
        self.is_staff = False
        self.is_superuser = False

    def __str__(self):
        return f"APIKeyUser({self.api_key.name})"


class APIKeyAuthentication(BaseAuthentication):
    """
    Authenticate via X-API-Key header.
    Usage: X-API-Key: qrg_xxxxxxxx
    """
    keyword = 'X-API-Key'

    def authenticate(self, request):
        api_key = request.META.get('HTTP_X_API_KEY')
        if not api_key:
            return None  # Let other auth backends try

        if not api_key.startswith('qrg_'):
            raise AuthenticationFailed('Invalid API key format.')

        hashed = APIKey.hash_key(api_key)
        try:
            key_obj = APIKey.objects.select_related('organization', 'created_by').get(
                hashed_key=hashed, is_active=True
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked API key.')

        if key_obj.is_expired():
            raise AuthenticationFailed('API key has expired.')

        # Update last used timestamp (fire-and-forget)
        APIKey.objects.filter(pk=key_obj.pk).update(last_used_at=timezone.now())

        user = APIKeyUser(key_obj)
        return (user, key_obj)

    def authenticate_header(self, request):
        return self.keyword
