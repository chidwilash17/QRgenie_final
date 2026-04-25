"""
Core Views — Auth, Users, Organizations, API Keys
====================================================
"""
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .models import Organization, APIKey, AuditLog, Invitation
from .serializers import (
    CustomTokenObtainPairSerializer, UserSerializer, RegisterSerializer,
    ChangePasswordSerializer, UpdateProfileSerializer,
    OrganizationSerializer, OrganizationUpdateSerializer,
    APIKeySerializer, APIKeyCreateSerializer,
    AuditLogSerializer, InvitationSerializer, InvitationCreateSerializer,
)
from .permissions import IsOrgOwnerOrAdmin, IsOrgMember
from .throttles import LoginRateThrottle, RegisterRateThrottle
from .utils import log_audit

User = get_user_model()


# ════════════════════════════════════════════════════════
# AUTH VIEWS
# ════════════════════════════════════════════════════════

class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ — Email+Password → JWT tokens."""
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            email = request.data.get('email', '')
            try:
                user = User.objects.get(email__iexact=email)
                if user.organization:
                    from .models import AuditLog as AL
                    from .utils import get_client_ip
                    AL.objects.create(
                        organization=user.organization,
                        user=user,
                        action='login',
                        resource_type='user',
                        resource_id=str(user.id),
                        details={},
                        ip_address=get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
            except Exception:
                pass
        return response


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — Create account + optional org."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class ClerkTokenExchangeView(APIView):
    """POST /api/v1/auth/clerk-exchange/ — Exchange Clerk token for JWT tokens."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .clerk_auth import ClerkAuthentication

        clerk_token = request.data.get('clerk_token')
        if not clerk_token:
            return Response({'detail': 'clerk_token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Use ClerkAuthentication to verify token and get/create user
            clerk_auth = ClerkAuthentication()
            user, _ = clerk_auth.authenticate_credentials(clerk_token)

            # Generate our JWT tokens for this user
            refresh = RefreshToken.for_user(user)

            return Response({
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — Blacklist refresh token."""
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            log_audit(request, 'logout', 'user', str(request.user.id) if request.user.is_authenticated else '')
            return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'detail': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)


class RefreshTokenView(TokenRefreshView):
    """POST /api/v1/auth/refresh/ — Refresh access token."""
    pass


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ — Current user profile."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return UpdateProfileSerializer
        return UserSerializer


class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'detail': 'Wrong current password.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        log_audit(request, 'password_changed', 'user', str(user.id))
        return Response({'detail': 'Password updated successfully.'})


# ════════════════════════════════════════════════════════
# USER MANAGEMENT VIEWS
# ════════════════════════════════════════════════════════

class UserListView(generics.ListAPIView):
    """GET /api/v1/users/ — List org members."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return User.objects.filter(organization=self.request.user.organization)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/users/<id>/ — Manage user."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        return User.objects.filter(organization=self.request.user.organization)

    def perform_destroy(self, instance):
        if instance.role == 'owner':
            raise serializers.ValidationError('Cannot delete the organization owner.')
        log_audit(self.request, 'user_deleted', 'user', str(instance.id), {'email': instance.email})
        instance.delete()


class InviteMemberView(APIView):
    """POST /api/v1/users/invite/ — Invite team member."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = request.user.organization
        if org.members.count() >= org.max_team_members:
            return Response(
                {'detail': f'Team member limit ({org.max_team_members}) reached. Upgrade your plan.'},
                status=status.HTTP_403_FORBIDDEN
            )

        invitation, created = Invitation.objects.update_or_create(
            organization=org,
            email=serializer.validated_data['email'],
            defaults={
                'invited_by': request.user,
                'role': serializer.validated_data['role'],
                'expires_at': timezone.now() + timedelta(days=7),
                'accepted': False,
            }
        )

        log_audit(request, 'member_invited', 'invitation', str(invitation.id), {
            'email': invitation.email, 'role': invitation.role
        })

        # TODO: Send invitation email via Celery task
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class AcceptInvitationView(APIView):
    """POST /api/v1/users/accept-invite/ — Accept invitation token."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')

        try:
            invitation = Invitation.objects.get(token=token, accepted=False)
        except Invitation.DoesNotExist:
            return Response({'detail': 'Invalid or expired invitation.'}, status=status.HTTP_400_BAD_REQUEST)

        if invitation.is_expired():
            return Response({'detail': 'Invitation has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create or link user
        user, created = User.objects.get_or_create(
            email=invitation.email,
            defaults={
                'username': invitation.email.split('@')[0],
                'first_name': first_name,
                'last_name': last_name,
                'organization': invitation.organization,
                'role': invitation.role,
            }
        )
        if created and password:
            user.set_password(password)
            user.save()
        elif not created:
            user.organization = invitation.organization
            user.role = invitation.role
            user.save()

        invitation.accepted = True
        invitation.save()

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


# ════════════════════════════════════════════════════════
# ORGANIZATION VIEWS
# ════════════════════════════════════════════════════════

class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/organizations/current/ — Manage current org."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return OrganizationUpdateSerializer
        return OrganizationSerializer

    def get_object(self):
        return self.request.user.organization


class OrganizationStatsView(APIView):
    """GET /api/v1/organizations/stats/ — Org usage stats."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = request.user.organization
        if not org:
            return Response({'detail': 'No organization.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.qrcodes.models import QRCode
        from apps.automation.models import Automation
        from apps.analytics.models import ScanEvent
        from django.utils import timezone as tz

        total_qr = QRCode.objects.filter(organization=org).count()
        active_qr = QRCode.objects.filter(organization=org, status='active').count()
        total_scans = ScanEvent.objects.filter(qr_code__organization=org).count()
        # Scans this calendar month
        now = tz.now()
        scans_this_month = ScanEvent.objects.filter(
            qr_code__organization=org,
            scanned_at__year=now.year,
            scanned_at__month=now.month,
        ).count()
        total_automations = Automation.objects.filter(organization=org).count()
        total_members = org.members.count()

        return Response({
            'total_qr_codes': total_qr,
            'active_qr_codes': active_qr,
            'total_scans': total_scans,
            'scans_this_month': scans_this_month,
            'team_members': total_members,
            'automations': total_automations,
        })


# ════════════════════════════════════════════════════════
# API KEY VIEWS
# ════════════════════════════════════════════════════════

class APIKeyListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/organizations/api-keys/"""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return APIKeyCreateSerializer
        return APIKeySerializer

    def get_queryset(self):
        return APIKey.objects.filter(organization=self.request.user.organization, is_active=True)

    def create(self, request, *args, **kwargs):
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plain_key, prefix, hashed_key = APIKey.generate_key()
        api_key = APIKey.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            name=serializer.validated_data['name'],
            prefix=prefix,
            hashed_key=hashed_key,
            scopes=serializer.validated_data.get('scopes', []),
            expires_at=serializer.validated_data.get('expires_at'),
        )

        log_audit(request, 'api_key_created', 'api_key', str(api_key.id), {'name': api_key.name})

        data = APIKeySerializer(api_key).data
        data['key'] = plain_key  # Show ONCE
        return Response(data, status=status.HTTP_201_CREATED)


class APIKeyRevokeView(generics.DestroyAPIView):
    """DELETE /api/v1/organizations/api-keys/<id>/"""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        return APIKey.objects.filter(organization=self.request.user.organization)

    def perform_destroy(self, instance):
        log_audit(self.request, 'api_key_revoked', 'api_key', str(instance.id), {'name': instance.name})
        instance.is_active = False
        instance.save()


# ════════════════════════════════════════════════════════
# AUDIT LOG VIEW
# ════════════════════════════════════════════════════════

class AuditLogListView(generics.ListAPIView):
    """GET /api/v1/organizations/audit-logs/ — View audit trail."""
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]
    filterset_fields = ['action', 'resource_type']
    search_fields = ['action', 'resource_type', 'user__email', 'ip_address']

    def get_queryset(self):
        return AuditLog.objects.filter(organization=self.request.user.organization).order_by('-created_at')
