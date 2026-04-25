"""
Custom DRF Throttle Classes
============================
Tight rate limits for high-risk auth endpoints to prevent brute-force attacks.
Scopes map to DEFAULT_THROTTLE_RATES in settings.py.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    5 login attempts per minute per IP — blocks password brute-force.
    Applied to POST /api/v1/auth/login/ regardless of auth state.
    """
    scope = 'login'


class RegisterRateThrottle(AnonRateThrottle):
    """
    10 registrations per hour per IP — blocks account-creation spam.
    Applied to POST /api/v1/auth/register/.
    """
    scope = 'register'


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    5 password-reset requests per hour per IP — blocks email enumeration spam.
    """
    scope = 'password_reset'
