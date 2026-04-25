"""
Clerk JWT Authentication for Django REST Framework
===================================================

This module provides authentication using Clerk JWTs.
Clerk is a user management service that handles login, registration, and user sessions.
"""

import jwt
import requests
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)
User = get_user_model()

# Cache for Clerk JWKS (JSON Web Key Set)
_jwks_cache = None


def get_clerk_jwks():
    """
    Fetch and cache Clerk's JSON Web Key Set for JWT verification.
    """
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = settings.CLERK_JWKS_URL
    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache
    except Exception as e:
        raise exceptions.AuthenticationFailed(f'Could not fetch Clerk JWKS: {e}')


def get_public_key_from_jwks(token):
    """
    Extract the public key from JWKS that matches the token's key ID.
    """
    try:
        # Get the key ID from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')

        if not kid:
            raise exceptions.AuthenticationFailed('Token missing key ID')

        jwks = get_clerk_jwks()
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)

        raise exceptions.AuthenticationFailed('Public key not found in JWKS')
    except jwt.exceptions.DecodeError:
        raise exceptions.AuthenticationFailed('Invalid token format')


class ClerkAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class for Clerk JWTs.

    Verifies the JWT token from the Authorization header,
    extracts user information, and creates/updates the user in Django.
    """

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        try:
            prefix, token = auth_header.split(' ')
            if prefix.lower() != 'bearer':
                return None
        except ValueError:
            return None

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token):
        try:
            # Get the public key for this token
            public_key = get_public_key_from_jwks(token)

            # Verify and decode the token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                options={
                    'verify_exp': True,
                    'verify_aud': False,  # Clerk doesn't always set audience
                }
            )

            logger.info(f"Clerk token payload: {payload}")

            # Extract user info from Clerk token
            clerk_user_id = payload.get('sub')
            if not clerk_user_id:
                raise exceptions.AuthenticationFailed('Token missing user ID')

            # Get or create user in Django
            user = self.get_or_create_user(payload)
            logger.info(f"Clerk authentication successful for user: {user.email} (ID: {user.id})")
            return (user, token)

        except jwt.ExpiredSignatureError:
            logger.warning("Clerk token expired")
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid Clerk token: {e}")
            raise exceptions.AuthenticationFailed(f'Invalid token: {e}')
        except Exception as e:
            logger.error(f"Clerk authentication error: {e}")
            raise exceptions.AuthenticationFailed(f'Authentication failed: {e}')

    def get_or_create_user(self, payload):
        """
        Get or create a Django user from Clerk token payload.
        """
        clerk_user_id = payload.get('sub')

        # Debug: Log the full payload structure to understand what Clerk sends
        logger.info(f"[DEBUG] Full Clerk JWT payload: {payload}")

        # Clerk JWT payload structure - check multiple field locations
        email_addresses = payload.get('email_addresses', [])
        primary_email = None

        # Try to extract email from email_addresses array
        if email_addresses and len(email_addresses) > 0:
            first_email_obj = email_addresses[0]
            if isinstance(first_email_obj, dict):
                primary_email = first_email_obj.get('email_address')
            elif isinstance(first_email_obj, str):  # Sometimes it's just a string
                primary_email = first_email_obj

        # Try multiple email field variations
        email_candidates = [
            primary_email,
            payload.get('email'),
            payload.get('primary_email_address'),
            payload.get('email_address'),  # Alternative field name
            payload.get('username') if '@' in str(payload.get('username', '')) else None,  # Sometimes username is email
        ]

        # Find first valid email
        email = None
        for candidate in email_candidates:
            if candidate and isinstance(candidate, str) and '@' in candidate:
                email = candidate.strip()
                break

        logger.info(f"[DEBUG] Extracted email: {email} from candidates: {email_candidates}")

        # Extract names with better fallbacks
        first_name = payload.get('first_name') or payload.get('given_name') or ''
        last_name = payload.get('last_name') or payload.get('family_name') or ''

        # Generate username from email or clerk_id
        if email:
            username_base = email.split('@')[0]
        else:
            username_base = f'clerk_user_{clerk_user_id[:8]}'

        # Ensure username is unique and valid
        username = username_base[:150]

        logger.info(f"[DEBUG] Username base: {username_base}, final username: {username}")

        # Try to find existing user by clerk_id or email
        user = None

        # First try to find by clerk_id (most reliable)
        if hasattr(User, 'clerk_id'):
            try:
                user = User.objects.get(clerk_id=clerk_user_id)
                logger.info(f"[DEBUG] Found existing user by clerk_id: {user.email}")
            except User.DoesNotExist:
                logger.info(f"[DEBUG] No user found with clerk_id: {clerk_user_id}")

        # Try to find by email if not found by clerk_id (only if email exists)
        if not user and email:
            try:
                user = User.objects.get(email=email)
                logger.info(f"[DEBUG] Found existing user by email: {user.email}")
                # Update clerk_id if missing
                if hasattr(user, 'clerk_id') and not user.clerk_id:
                    user.clerk_id = clerk_user_id
                    user.save(update_fields=['clerk_id'])
            except User.DoesNotExist:
                logger.info(f"[DEBUG] No user found with email: {email}")
            except User.MultipleObjectsReturned:
                # Multiple users with same email - get the first one and link it
                user = User.objects.filter(email=email).first()
                logger.info(f"[DEBUG] Multiple users found with email, using first: {user.email}")
                if hasattr(user, 'clerk_id') and not user.clerk_id:
                    user.clerk_id = clerk_user_id
                    user.save(update_fields=['clerk_id'])

        # Create new user if not found
        if not user:
            logger.info(f"[DEBUG] Creating new user for clerk_id: {clerk_user_id}")

            # Make username unique
            original_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1
                if len(username) > 150:
                    username = f"clerk_{counter}"

            try:
                # Create default organization for new Clerk users
                from .models import Organization
                from django.utils.text import slugify

                # Create organization name - handle case where email is missing during sign-up
                if email:
                    org_name = f"{first_name} {last_name}".strip() or email.split('@')[0]
                    user_email = email
                else:
                    # Email missing during sign-up - create temporary email that can be updated later
                    org_name = f"{first_name} {last_name}".strip() or f"User {clerk_user_id[:8]}"
                    user_email = f'clerk_{clerk_user_id}@temporary.local'
                    logger.warning(f"[DEBUG] Email missing during sign-up, using temporary: {user_email}")

                org_slug = slugify(org_name)

                # Ensure unique slug
                base_slug = org_slug
                counter = 1
                while Organization.objects.filter(slug=org_slug).exists():
                    org_slug = f"{base_slug}-{counter}"
                    counter += 1

                organization = Organization.objects.create(
                    name=org_name,
                    slug=org_slug
                )

                user = User.objects.create(
                    email=user_email,
                    username=username,
                    first_name=first_name[:150] if first_name else '',
                    last_name=last_name[:150] if last_name else '',
                    is_active=True,
                    organization=organization,
                    role='owner',  # New Clerk users become organization owners
                )

                # Set clerk_id if the field exists
                if hasattr(user, 'clerk_id'):
                    user.clerk_id = clerk_user_id
                    user.save(update_fields=['clerk_id'])

                logger.info(f"Created new organization '{org_name}' ({organization.id}) for Clerk user {user.email}")

            except Exception as e:
                logger.error(f"[DEBUG] Failed to create user: {e}")
                # If user creation fails, try to find existing user one more time
                if email:
                    try:
                        user = User.objects.get(email=email)
                        logger.info(f"[DEBUG] Found existing user after creation failure: {user.email}")
                    except User.DoesNotExist:
                        raise exceptions.AuthenticationFailed(f'Failed to create user: {e}')
                else:
                    raise exceptions.AuthenticationFailed(f'Failed to create user without email: {e}')
        else:
            logger.info(f"[DEBUG] User already exists: {user.email}")
            # Update user info from Clerk if user exists
            updated_fields = []
            if first_name and user.first_name != first_name:
                user.first_name = first_name[:150]
                updated_fields.append('first_name')
            if last_name and user.last_name != last_name:
                user.last_name = last_name[:150]
                updated_fields.append('last_name')

            # Update email if we now have a real email and user currently has temporary email
            if email and (user.email.endswith('@temporary.local') or user.email != email):
                # Only update email if it's not already taken by another user
                if not User.objects.filter(email=email).exclude(id=user.id).exists():
                    logger.info(f"[DEBUG] Updating user email from {user.email} to {email}")
                    user.email = email
                    updated_fields.append('email')

            # Ensure existing Clerk users have an organization
            if not user.organization:
                try:
                    from .models import Organization
                    from django.utils.text import slugify
                    org_name = f"{user.first_name} {user.last_name}".strip() or (user.email.split('@')[0] if not user.email.endswith('@temporary.local') else f"User {clerk_user_id[:8]}")
                    org_slug = slugify(org_name)

                    # Ensure unique slug
                    base_slug = org_slug
                    counter = 1
                    while Organization.objects.filter(slug=org_slug).exists():
                        org_slug = f"{base_slug}-{counter}"
                        counter += 1

                    organization = Organization.objects.create(
                        name=org_name,
                        slug=org_slug
                    )

                    user.organization = organization
                    user.role = 'owner'
                    updated_fields.extend(['organization', 'role'])
                    logger.info(f"Created organization '{org_name}' for existing Clerk user {user.email}")
                except Exception as e:
                    logger.warning(f"Failed to create organization for user {user.email}: {e}")

            if updated_fields:
                try:
                    user.save(update_fields=updated_fields)
                    logger.info(f"[DEBUG] Updated user fields: {updated_fields}")
                except Exception as e:
                    logger.warning(f"[DEBUG] Failed to update user fields: {e}")
                    # If update fails, continue with existing user data
                    pass

        logger.info(f"[DEBUG] Final user result: ID={user.id}, email={user.email}, organization={user.organization.name if user.organization else 'None'}")
        return user

    def authenticate_header(self, request):
        return 'Bearer'
