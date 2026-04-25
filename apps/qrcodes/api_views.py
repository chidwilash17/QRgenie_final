"""
Developer REST API Views
==========================
Public-facing API endpoints authenticated via API key (X-API-Key header).
Provides CRUD for QR codes and read access to scan analytics.
"""
import json
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.authentication import APIKeyAuthentication
from apps.core.permissions import HasAPIKeyScope
from apps.core.utils import log_audit
from .models import QRCode, QRVersion
from .serializers import (
    QRCodeListSerializer, QRCodeDetailSerializer, QRCodeCreateSerializer,
    _make_json_safe,
)


class DevAPIBase:
    """Mixin for all developer API views."""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKeyScope]


# ── List / Create QR Codes ────────────────────────────
class DevQRListCreateView(DevAPIBase, generics.ListCreateAPIView):
    """
    GET  /api/v1/developer/qr/  - List QR codes
    POST /api/v1/developer/qr/  - Create a QR code

    Required scopes: qr:read (GET), qr:create (POST)
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'qr_type', 'folder']
    search_fields = ['title', 'slug', 'description', 'tags']
    ordering_fields = ['created_at', 'updated_at', 'total_scans']
    ordering = ['-created_at']

    @property
    def required_scopes(self):
        if self.request.method == 'GET':
            return ['qr:read']
        return ['qr:create']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QRCodeCreateSerializer
        return QRCodeListSerializer

    def get_queryset(self):
        return QRCode.objects.filter(
            organization=self.request.user.organization
        ).select_related('created_by')

    def perform_create(self, serializer):
        api_key = self.request.auth
        qr = serializer.save(
            organization=self.request.user.organization,
            created_by=api_key.created_by,
        )
        log_audit(self.request, 'qr_created_via_api', 'qr_code', str(qr.id), {
            'title': qr.title, 'api_key': api_key.name,
        })


# ── Retrieve / Update / Delete QR Code ───────────────
class DevQRDetailView(DevAPIBase, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/developer/qr/<id>/  - Get QR details
    PUT    /api/v1/developer/qr/<id>/  - Full update
    PATCH  /api/v1/developer/qr/<id>/  - Partial update
    DELETE /api/v1/developer/qr/<id>/  - Delete (archive)

    Required scopes: qr:read (GET), qr:update (PUT/PATCH), qr:delete (DELETE)
    """
    lookup_field = 'id'

    @property
    def required_scopes(self):
        if self.request.method == 'GET':
            return ['qr:read']
        if self.request.method == 'DELETE':
            return ['qr:delete']
        return ['qr:update']

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return QRCodeCreateSerializer
        return QRCodeDetailSerializer

    def get_queryset(self):
        return QRCode.objects.filter(
            organization=self.request.user.organization
        ).select_related('created_by')

    def perform_destroy(self, instance):
        api_key = self.request.auth
        instance.status = 'archived'
        instance.save(update_fields=['status'])
        log_audit(self.request, 'qr_archived_via_api', 'qr_code', str(instance.id), {
            'title': instance.title, 'api_key': api_key.name,
        })


# ── Scan Analytics ────────────────────────────────────
class DevQRAnalyticsView(DevAPIBase, APIView):
    """
    GET /api/v1/developer/qr/<id>/analytics/

    Returns scan stats for a QR code.
    Required scopes: analytics:read
    """
    required_scopes = ['analytics:read']

    def get(self, request, id):
        try:
            qr = QRCode.objects.get(id=id, organization=request.user.organization)
        except QRCode.DoesNotExist:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Basic stats always available
        data = {
            'id': str(qr.id),
            'title': qr.title,
            'slug': qr.slug,
            'total_scans': qr.total_scans,
            'unique_scans': qr.unique_scans,
            'status': qr.status,
            'created_at': qr.created_at.isoformat(),
        }

        # Try to get detailed analytics if the analytics app has data
        try:
            from apps.analytics.models import ScanEvent
            from django.db.models import Count
            from django.db.models.functions import TruncDate

            scans_qs = ScanEvent.objects.filter(qr_code=qr)

            # Scans by day (last 30 days)
            thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
            daily = (
                scans_qs.filter(scanned_at__gte=thirty_days_ago)
                .annotate(date=TruncDate('scanned_at'))
                .values('date')
                .annotate(count=Count('id'))
                .order_by('date')
            )
            data['scans_by_day'] = [
                {'date': str(d['date']), 'count': d['count']} for d in daily
            ]

            # Top countries
            countries = (
                scans_qs.values('country')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            )
            data['top_countries'] = [
                {'country': c['country'] or 'Unknown', 'count': c['count']} for c in countries
            ]

            # Top devices
            devices = (
                scans_qs.values('device_type')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
            )
            data['top_devices'] = [
                {'device': d['device_type'] or 'Unknown', 'count': d['count']} for d in devices
            ]
        except Exception:
            # Analytics module not available or no data
            data['scans_by_day'] = []
            data['top_countries'] = []
            data['top_devices'] = []

        return Response(data)


# ── Bulk Analytics (all QRs) ─────────────────────────
class DevQRBulkAnalyticsView(DevAPIBase, APIView):
    """
    GET /api/v1/developer/analytics/summary/

    Returns aggregated scan stats for the entire organization.
    Required scopes: analytics:read
    """
    required_scopes = ['analytics:read']

    def get(self, request):
        org = request.user.organization
        qr_codes = QRCode.objects.filter(organization=org)

        total_qr = qr_codes.count()
        total_scans = sum(q.total_scans for q in qr_codes.only('total_scans'))
        total_unique = sum(q.unique_scans for q in qr_codes.only('unique_scans'))

        active = qr_codes.filter(status='active').count()
        paused = qr_codes.filter(status='paused').count()
        archived = qr_codes.filter(status='archived').count()

        # Top performing QR codes
        top_qrs = qr_codes.order_by('-total_scans')[:10]
        top_list = [
            {
                'id': str(q.id),
                'title': q.title,
                'slug': q.slug,
                'total_scans': q.total_scans,
                'unique_scans': q.unique_scans,
            }
            for q in top_qrs
        ]

        return Response({
            'total_qr_codes': total_qr,
            'total_scans': total_scans,
            'total_unique_scans': total_unique,
            'by_status': {
                'active': active,
                'paused': paused,
                'archived': archived,
            },
            'top_qr_codes': top_list,
        })


# ── API Info / Docs Endpoint ─────────────────────────
class DevAPIInfoView(DevAPIBase, APIView):
    """
    GET /api/v1/developer/info/

    Returns API info and available scopes. No special scope required.
    """
    required_scopes = []

    def get(self, request):
        api_key = request.auth
        return Response({
            'api_version': 'v1',
            'key_name': api_key.name,
            'key_prefix': api_key.prefix,
            'scopes': api_key.scopes,
            'organization': str(api_key.organization.name),
            'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
            'available_scopes': [
                'qr:create', 'qr:read', 'qr:update', 'qr:delete',
                'analytics:read', '*',
            ],
            'endpoints': {
                'list_qr_codes': 'GET /api/v1/developer/qr/',
                'create_qr_code': 'POST /api/v1/developer/qr/',
                'get_qr_code': 'GET /api/v1/developer/qr/{id}/',
                'update_qr_code': 'PUT/PATCH /api/v1/developer/qr/{id}/',
                'delete_qr_code': 'DELETE /api/v1/developer/qr/{id}/',
                'qr_analytics': 'GET /api/v1/developer/qr/{id}/analytics/',
                'org_analytics': 'GET /api/v1/developer/analytics/summary/',
                'api_info': 'GET /api/v1/developer/info/',
            },
            'rate_limits': {
                'requests_per_hour': 1000,
            },
        })
