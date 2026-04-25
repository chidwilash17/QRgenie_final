"""
QR Codes Views  CRUD, Bulk Upload, Archive, Export, Password Verify
=====================================================================
"""
import io
import json
import os
import re
import uuid
import zipfile
import logging
import qrcode
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import F as DBF, Q

logger = logging.getLogger('apps.qrcodes')
from django.utils import timezone
from rest_framework import generics, permissions, status, filters, parsers

# ── Upload security helpers ────────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    """
    Strip any directory component from an uploaded filename to prevent
    path traversal attacks (e.g. '../../config/settings.py' → 'settings.py').
    Falls back to 'upload' if basename is empty.
    """
    from django.utils.text import get_valid_filename
    base = os.path.basename(name.replace('\\', '/'))
    safe = get_valid_filename(base) if base else 'upload'
    return safe or 'upload'

# Magic-byte prefixes that indicate dangerous or executable content that must
# never be saved to disk regardless of file extension.
_DANGEROUS_MAGIC = [
    b'<?php',          # PHP script
    b'<html',          # HTML (case-insensitive checked below)
    b'<!doc',          # HTML doctype
    b'<scri',          # <script> tag
    b'\x4d\x5a',       # Windows PE / .exe / .dll
    b'\x7fELF',        # Linux ELF executable
    b'#!/',            # Unix shebang
]

def _check_not_dangerous(file) -> bool:
    """
    Read the first 32 bytes and reject files whose content matches known
    dangerous patterns (executables, scripts, HTML).
    Returns True if the file appears safe, False if it should be rejected.
    Resets the read pointer to the beginning afterwards.
    """
    header = file.read(32)
    file.seek(0)
    header_lower = header.lower()
    for pattern in _DANGEROUS_MAGIC:
        if header_lower[:len(pattern)] == pattern.lower():
            return False
    return True

def _check_pdf_magic(file) -> bool:
    """Return True only if the file starts with the PDF magic bytes %PDF-."""
    header = file.read(5)
    file.seek(0)
    return header == b'%PDF-'

def _check_image_magic(file) -> bool:
    """Return True if the file starts with a known image format magic sequence."""
    header = file.read(12)
    file.seek(0)
    return (
        header[:3] == b'\xff\xd8\xff'     # JPEG
        or header[:4] == b'\x89PNG'       # PNG
        or header[:4] in (b'GIF8', )      # GIF87a / GIF89a
        or (header[:4] == b'RIFF' and header[8:12] == b'WEBP')  # WebP
    )
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from apps.core.permissions import IsOrgMember, IsOrgEditor, IsOrgOwnerOrAdmin
from apps.core.utils import log_audit
from apps.landing_pages.models import LandingPage
from .models import (
    QRCode, QRVersion, RoutingRule, MultiLinkItem,
    FileAttachment, PaymentConfig, ChatConfig, BulkUploadJob, RotationSchedule,
    LanguageRoute, TimeSchedule, PDFDocument, VideoDocument, DeviceRoute,
    GeoFenceRule, ABTest, DeepLink, TokenRedirect, QRExpiry, ScanAlert,
    LoyaltyProgram, LoyaltyMember, DigitalVCard,
    ProductAuth, ProductSerial,
    DocumentUploadForm, DocumentSubmission, DocumentFile,
    FunnelConfig, FunnelStep, FunnelSession,
    QRCodeAccess,
)
from .serializers import (
    QRCodeListSerializer, QRCodeDetailSerializer, QRCodeCreateSerializer,
    RoutingRuleSerializer, MultiLinkItemSerializer,
    FileAttachmentSerializer, PaymentConfigSerializer, ChatConfigSerializer,
    BulkUploadJobSerializer, QRVersionSerializer, RotationScheduleSerializer,
    LanguageRouteSerializer, TimeScheduleSerializer, PDFDocumentSerializer,
    VideoDocumentSerializer, DeviceRouteSerializer,
    GeoFenceRuleSerializer, ABTestSerializer, DeepLinkSerializer,
    TokenRedirectSerializer, QRExpirySerializer, ScanAlertSerializer,
    LoyaltyProgramSerializer, LoyaltyMemberSerializer, DigitalVCardSerializer,
    ProductAuthSerializer, ProductSerialSerializer,
    DocumentUploadFormSerializer, DocumentSubmissionSerializer, DocumentFileSerializer,
    FunnelConfigSerializer, FunnelStepSerializer, FunnelSessionSerializer,
    QRCodeAccessSerializer,
)
from .services import generate_qr_image, generate_qr_svg, generate_qr_pdf, generate_qr_jpg, _dpi_to_box_size, process_bulk_upload, generate_poster, POSTER_PRESETS, get_all_feature_status, detect_feature_conflicts, simulate_redirect


def _get_qr_with_access(request, qr_id):
    """Return QR if user is in same org, is the creator, or has QRCodeAccess."""
    try:
        qr = QRCode.objects.get(id=qr_id)
    except QRCode.DoesNotExist:
        return None
    if qr.organization == request.user.organization:
        return qr
    if qr.created_by == request.user:
        return qr
    if QRCodeAccess.objects.filter(qr_code=qr, user=request.user).exists():
        return qr
    return None


def _check_frozen(qr, request):
    """Return an error Response if the QR is frozen and the user is not owner/admin, else None."""
    if qr and qr.is_frozen and request.user.role not in ('owner', 'admin'):
        return Response(
            {'detail': 'This QR code is frozen. Only an admin or owner can edit it.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None



# 
# QR CODE CRUD
# 

class QRCodeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/qr/            List all QR codes for org
    POST /api/v1/qr/            Create a new QR code
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['qr_type', 'status', 'folder']
    search_fields = ['title', 'slug', 'description', 'tags']
    ordering_fields = ['created_at', 'total_scans', 'title']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QRCodeCreateSerializer
        return QRCodeListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = QRCode.objects.filter(
            Q(organization=user.organization) |
            Q(id__in=QRCodeAccess.objects.filter(user=user).values_list('qr_code_id', flat=True))
        ).distinct()
        # Exclude archived by default
        if self.request.query_params.get('include_archived') != 'true':
            qs = qs.exclude(status='archived')
        tag = self.request.query_params.get('tag')
        if tag:
            qs = qs.filter(tags__contains=[tag])
        return qs

    def perform_create(self, serializer):
        org = self.request.user.organization
        # Check limits
        current_count = QRCode.objects.filter(organization=org).exclude(status='archived').count()
        if current_count >= org.max_qr_codes:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {'detail': f'QR code limit reached ({current_count}/{org.max_qr_codes}). '
                           f'Archive or delete existing QR codes, or upgrade your plan.'}
            )

        password = self.request.data.get('password')
        qr = serializer.save(
            organization=org,
            created_by=self.request.user,
        )

        # Generate QR image  wrapped so a generation error never fails the create
        try:
            img_url = generate_qr_image(qr)
            qr.qr_image_url = img_url
            qr.save(update_fields=['qr_image_url'])
        except Exception as exc:
            logger.error('QR image generation failed for %s: %s', qr.id, exc, exc_info=True)
            # Continue without an image  the QR record is still created

        # Auto-create a default LandingPage for every new QR code
        if True:
            import re, uuid as _uuid
            base_slug = re.sub(r'[^a-z0-9]+', '-', qr.title.lower()).strip('-') or 'page'
            lp_slug = base_slug
            # Ensure unique slug
            if LandingPage.objects.filter(slug=lp_slug).exists():
                lp_slug = f"{base_slug}-{str(_uuid.uuid4())[:8]}"
            default_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{qr.title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{{background:#0d0d0d;color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:sans-serif}}.card{{background:#1a1a2e;border:1px solid #333;border-radius:16px;padding:2rem;text-align:center;max-width:480px;width:100%}}</style>
</head>
<body>
<div class="card">
  <h1 class="mb-3">{qr.title}</h1>
  <p class="text-muted">Your landing page is ready. Use &ldquo;Change Design&rdquo; to pick a template.</p>
</div>
</body></html>"""
            LandingPage.objects.create(
                organization=org,
                qr_code=qr,
                created_by=self.request.user,
                title=qr.title,
                slug=lp_slug,
                html_content=default_html,
                is_published=True,
                page_config={'page_type': 'bio_link', 'form_data': {}, 'template_id': ''},
            )

        log_audit(self.request, 'qr_created', 'qr_code', str(qr.id), {
            'title': qr.title, 'type': qr.qr_type, 'slug': qr.slug,
        })

        # ── Fire automation trigger: qr_created ──
        try:
            from apps.automation.tasks import fire_automation_trigger
            fire_automation_trigger(
                trigger_type='qr_created',
                context={
                    'qr_id': str(qr.id),
                    'title': qr.title,
                    'qr_type': qr.qr_type,
                    'slug': qr.slug,
                    'destination_url': qr.destination_url or '',
                    'created_by': self.request.user.email,
                },
                org_id=str(org.id),
                qr_id=str(qr.id),
            )
        except Exception as exc:
            logger.error(f'Automation trigger qr_created failed: {exc}')

    def create(self, request, *args, **kwargs):
        """Override to return QRCodeDetailSerializer in the response (includes id)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Re-fetch and serialize with detail serializer so `id` is included
        qr = serializer.instance
        qr.refresh_from_db()
        out = QRCodeDetailSerializer(qr).data
        return Response(out, status=status.HTTP_201_CREATED)


class QRCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/qr/<id>/               QR detail with rules, links, versions
    GET    /api/v1/qr/<id>/?export=png    Download QR image (png|svg|pdf|jpg)
    PATCH  /api/v1/qr/<id>/               Update QR
    DELETE /api/v1/qr/<id>/               Permanently delete QR
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return QRCodeCreateSerializer
        return QRCodeDetailSerializer

    def get_queryset(self):
        user = self.request.user
        return QRCode.objects.filter(
            Q(organization=user.organization) |
            Q(id__in=QRCodeAccess.objects.filter(user=user).values_list('qr_code_id', flat=True))
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        """If ?export= is present, return QR image instead of JSON detail."""
        fmt = request.query_params.get('export', '').lower()
        if fmt and fmt in ('png', 'svg', 'pdf', 'jpg'):
            qr = self.get_object()
            try:
                dpi = max(72, min(1200, int(request.query_params.get('dpi', '150'))))
            except (ValueError, TypeError):
                dpi = 150
            box_size = _dpi_to_box_size(dpi)
            try:
                if fmt == 'svg':
                    data = generate_qr_svg(qr)
                    response = HttpResponse(data, content_type='image/svg+xml')
                    response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.svg"'
                    return response
                if fmt == 'pdf':
                    data = generate_qr_pdf(qr, box_size=box_size, dpi=dpi)
                    response = HttpResponse(data, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.pdf"'
                    return response
                if fmt == 'jpg':
                    data = generate_qr_jpg(qr, dpi=dpi)
                    response = HttpResponse(data, content_type='image/jpeg')
                    response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.jpg"'
                    return response
                # Default: PNG
                img = generate_qr_image(qr, return_image=True, box_size=box_size)
                buf = io.BytesIO()
                img.save(buf, format='PNG', dpi=(dpi, dpi))
                buf.seek(0)
                response = HttpResponse(buf.getvalue(), content_type='image/png')
                response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.png"'
                return response
            except Exception as exc:
                import traceback
                logger.error('QR export failed for %s: %s\n%s', qr.slug, exc, traceback.format_exc())
                return Response({'detail': f'QR generation failed: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return super().retrieve(request, *args, **kwargs)

    def perform_update(self, serializer):
        qr = self.get_object()
        # Freeze guard  only owner/admin can edit a frozen QR
        if qr.is_frozen and self.request.user.role not in ('owner', 'admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('This QR code is frozen. Only an admin or owner can edit it.')
        # Snapshot *before* saving changes (round-trip to make UUIDs/dates JSON-safe)
        old_snapshot = json.loads(json.dumps(QRCodeDetailSerializer(qr).data, default=str))
        qr = serializer.save()
        # Regenerate QR image if colors/logo changed
        img_url = generate_qr_image(qr)
        qr.qr_image_url = img_url

        # Create version history entry
        qr.current_version += 1
        qr.save(update_fields=['qr_image_url', 'current_version'])

        # Build a change summary from the fields that changed
        changed = [k for k in serializer.validated_data if k not in ('multi_links', 'payment_config', 'chat_config', 'rules')]
        summary = 'Updated ' + ', '.join(changed[:5]) if changed else 'Updated'

        QRVersion.objects.create(
            qr_code=qr,
            version_number=qr.current_version,
            snapshot=old_snapshot,
            changed_by=self.request.user,
            change_summary=summary,
        )

        log_audit(self.request, 'qr_updated', 'qr_code', str(qr.id), {'title': qr.title})

    def perform_destroy(self, instance):
        log_audit(self.request, 'qr_deleted', 'qr_code', str(instance.id), {'title': instance.title})
        instance.delete()


# 
# ARCHIVE / STATUS MANAGEMENT
# 

class QRCodeArchiveView(APIView):
    """POST /api/v1/qr/<id>/archive/  Archive a QR code."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen

        qr.status = 'archived'
        qr.save(update_fields=['status'])
        log_audit(request, 'qr_archived', 'qr_code', str(qr.id))
        return Response({'detail': 'QR code archived.'})


class QRCodeRestoreView(APIView):
    """POST /api/v1/qr/<id>/restore/  Restore archived QR."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr or qr.status != 'archived':
            return Response({'detail': 'Archived QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        qr.status = 'active'
        qr.save(update_fields=['status'])
        log_audit(request, 'qr_restored', 'qr_code', str(qr.id))
        return Response({'detail': 'QR code restored.'})


class QRCodePauseView(APIView):
    """POST /api/v1/qr/<id>/pause/  Pause QR code scanning."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen

        qr.status = 'paused' if qr.status == 'active' else 'active'
        qr.save(update_fields=['status'])
        # Invalidate redirect cache so status change takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, f'qr_{"paused" if qr.status == "paused" else "activated"}', 'qr_code', str(qr.id))
        return Response({'detail': f'QR code {qr.status}.', 'status': qr.status})



class QRCodeFreezeView(APIView):
    """POST /api/v1/qr/<id>/freeze/ - Toggle freeze on a QR code."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Only org owner/admin OR the QR creator can freeze/unfreeze
        is_org_admin = request.user.role in ('owner', 'admin')
        is_creator = qr.created_by_id == request.user.id
        if not is_org_admin and not is_creator:
            return Response({'detail': 'Only the QR creator or an admin can freeze/unfreeze.'}, status=status.HTTP_403_FORBIDDEN)

        if qr.is_frozen:
            qr.is_frozen = False
            qr.frozen_by = None
            qr.frozen_at = None
            qr.save(update_fields=['is_frozen', 'frozen_by', 'frozen_at'])
            log_audit(request, 'qr_unfrozen', 'qr_code', str(qr.id))
            return Response({'detail': 'QR code unfrozen.', 'is_frozen': False})
        else:
            qr.is_frozen = True
            qr.frozen_by = request.user
            qr.frozen_at = timezone.now()
            qr.save(update_fields=['is_frozen', 'frozen_by', 'frozen_at'])
            log_audit(request, 'qr_frozen', 'qr_code', str(qr.id))
            return Response({'detail': 'QR code frozen.', 'is_frozen': True})


# 
# ROUTING RULES
# 

class RoutingRuleListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/qr/<qr_id>/rules/   List rules
    POST /api/v1/qr/<qr_id>/rules/   Add rule
    """
    serializer_class = RoutingRuleSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def get_queryset(self):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            return RoutingRule.objects.none()
        return RoutingRule.objects.filter(qr_code=qr)

    def perform_create(self, serializer):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            raise Http404('QR code not found')
        serializer.save(qr_code=qr)
        log_audit(self.request, 'rule_created', 'routing_rule', str(serializer.instance.id), {
            'qr_id': str(qr.id), 'rule_type': serializer.instance.rule_type,
        })


class RoutingRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/qr/<qr_id>/rules/<id>/"""
    serializer_class = RoutingRuleSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    lookup_field = 'id'

    def get_queryset(self):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            return RoutingRule.objects.none()
        return RoutingRule.objects.filter(qr_code=qr)


# 
# MULTI-LINK MANAGEMENT
# 

class MultiLinkListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/qr/<qr_id>/links/"""
    serializer_class = MultiLinkItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def get_queryset(self):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            return MultiLinkItem.objects.none()
        return MultiLinkItem.objects.filter(qr_code=qr)

    def perform_create(self, serializer):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            raise Http404('QR code not found')
        serializer.save(qr_code=qr)


class MultiLinkDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/qr/<qr_id>/links/<id>/"""
    serializer_class = MultiLinkItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    lookup_field = 'id'

    def get_queryset(self):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            return MultiLinkItem.objects.none()
        return MultiLinkItem.objects.filter(qr_code=qr)


# 
# FILE UPLOAD / MANAGEMENT
# 

class FileUploadView(APIView):
    """POST /api/v1/qr/<qr_id>/files/  Upload file for file-type QR."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, qr_id):
        try:
            qr = _get_qr_with_access(request, qr_id)
        except QRCode.DoesNotExist:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save file to media directory (for dev; production uses MinIO/S3)
        import os
        from django.conf import settings
        if not _check_not_dangerous(file):
            return Response({'detail': 'File content is not allowed.'}, status=status.HTTP_400_BAD_REQUEST)
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'qr_files', str(qr.id))
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = _sanitize_filename(file.name)
        file_path = os.path.join(upload_dir, safe_name)

        with open(file_path, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        file_url = f"{settings.MEDIA_URL}qr_files/{qr.id}/{safe_name}"

        # Mark old files as non-current
        FileAttachment.objects.filter(qr_code=qr, is_current=True).update(is_current=False)

        # Get next version number
        latest = FileAttachment.objects.filter(qr_code=qr).order_by('-version').first()
        next_version = (latest.version + 1) if latest else 1

        attachment = FileAttachment.objects.create(
            qr_code=qr,
            file_name=file.name,
            file_url=file_url,
            file_size=file.size,
            mime_type=file.content_type or '',
            version=next_version,
            is_current=True,
            uploaded_by=request.user,
        )

        log_audit(request, 'file_uploaded', 'file_attachment', str(attachment.id), {
            'qr_id': str(qr.id), 'file_name': file.name, 'version': next_version,
        })

        return Response(FileAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


# 
# QR IMAGE DOWNLOAD & EXPORT
# 

class QRCodeDownloadImageView(APIView):
    """GET /api/v1/qr/<id>/download/?format=png|svg|pdf&dpi=150"""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get(self, request, id):
        # Lookup using the same pattern as QRCodeDetailView
        org = getattr(request.user, 'organization', None)
        logger.info('Download request: qr=%s user=%s org=%s', id, request.user, org)
        try:
            qr = _get_qr_with_access(request, id)
        except QRCode.DoesNotExist:
            # Log all QRs with this id (regardless of org) to see if it's an org mismatch
            exists_any = QRCode.objects.filter(id=id).exists()
            logger.warning(
                'Download 404: qr=%s org=%s exists_any=%s',
                id, org, exists_any,
            )
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        fmt = request.query_params.get('format', 'png').lower()

        # DPI-aware sizing  default 150 for screen, up to 1200 for large-format print
        try:
            dpi = max(72, min(1200, int(request.query_params.get('dpi', '150'))))
        except (ValueError, TypeError):
            dpi = 150
        box_size = _dpi_to_box_size(dpi)

        try:
            if fmt == 'svg':
                data = generate_qr_svg(qr)
                response = HttpResponse(data, content_type='image/svg+xml')
                response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.svg"'
                return response

            if fmt == 'pdf':
                data = generate_qr_pdf(qr, box_size=box_size, dpi=dpi)
                response = HttpResponse(data, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.pdf"'
                return response

            if fmt == 'jpg':
                data = generate_qr_jpg(qr, dpi=dpi)
                response = HttpResponse(data, content_type='image/jpeg')
                response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.jpg"'
                return response

            # Default: PNG
            img = generate_qr_image(qr, return_image=True, box_size=box_size)
            buf = io.BytesIO()
            img.save(buf, format='PNG', dpi=(dpi, dpi))
            buf.seek(0)
            response = HttpResponse(buf.getvalue(), content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="qr_{qr.slug}.png"'
            return response

        except Exception as exc:
            import traceback
            logger.error(
                'QR download failed for %s (fmt=%s dpi=%s): %s\n%s',
                qr.slug, fmt, dpi, exc, traceback.format_exc(),
            )
            return Response(
                {'detail': f'QR generation failed: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QRLogoUploadView(APIView):
    """
    POST /api/v1/qr/logo-upload/
    Upload a logo image file; returns {"logo_url": "<media-url>"}
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('logo')
        if not file:
            return Response({'detail': 'No file provided. Use field name "logo".'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate mime type
        allowed = ('image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif')
        mime = file.content_type or ''
        if mime not in allowed:
            return Response({'detail': f'Unsupported file type: {mime}. Allowed: PNG, JPEG, WEBP, GIF.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Save with a unique filename
        ext = os.path.splitext(file.name)[1].lower() or '.png'
        filename = f"{uuid.uuid4().hex}{ext}"
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'qr_logos')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        logo_url = request.build_absolute_uri(f"{settings.MEDIA_URL}qr_logos/{filename}")
        return Response({'logo_url': logo_url}, status=status.HTTP_201_CREATED)


class QRCodeExportZipView(APIView):
    """POST /api/v1/qr/export/ -- Export multiple (or all) QRs as ZIP."""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        qr_ids = request.data.get('qr_ids', [])
        export_all = request.data.get('export_all', False)

        if not qr_ids and not export_all:
            return Response({'detail': 'Provide qr_ids or set export_all to true.'}, status=status.HTTP_400_BAD_REQUEST)

        qrs = QRCode.objects.filter(organization=request.user.organization)
        if not export_all:
            qrs = qrs.filter(id__in=qr_ids)

        if not qrs.exists():
            return Response({'detail': 'No QR codes found.'}, status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        all_meta = []
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for qr in qrs:
                try:
                    img = generate_qr_image(qr, return_image=True)
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    zf.writestr(f"images/{qr.slug}.png", img_buffer.getvalue())
                except Exception:
                    pass

                meta = {
                    'id': str(qr.id),
                    'title': qr.title,
                    'slug': qr.slug,
                    'short_url': qr.short_url,
                    'destination_url': qr.destination_url or '',
                    'qr_type': qr.qr_type,
                    'status': qr.status,
                    'tags': qr.tags or [],
                    'total_scans': qr.total_scans,
                    'unique_scans': qr.unique_scans,
                    'is_dynamic': qr.is_dynamic,
                    'is_frozen': qr.is_frozen,
                    'created_at': qr.created_at.isoformat(),
                    'updated_at': qr.updated_at.isoformat(),
                }
                all_meta.append(meta)
                zf.writestr(f"metadata/{qr.slug}.json", json.dumps(meta, indent=2))

            import csv as csv_mod
            csv_buf = io.StringIO()
            writer = csv_mod.writer(csv_buf)
            writer.writerow(['title', 'slug', 'qr_type', 'destination_url', 'status', 'tags', 'total_scans', 'unique_scans', 'created_at'])
            for m in all_meta:
                writer.writerow([m['title'], m['slug'], m['qr_type'], m['destination_url'], m['status'],
                                 ','.join(m['tags']), m['total_scans'], m['unique_scans'], m['created_at']])
            zf.writestr('qr_codes_summary.csv', csv_buf.getvalue())

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="qrgenie_export_{timezone.now().strftime("%Y%m%d")}.zip"'
        log_audit(request, 'qr_export_zip', 'organization', str(request.user.organization_id),
                  {'count': len(all_meta), 'export_all': export_all})
        return response


# 
# BULK UPLOAD
# 

class BulkUploadView(APIView):
    """POST /api/v1/qr/bulk-upload/  Upload Excel for bulk QR creation."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    parser_classes = [MultiPartParser]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.endswith(('.xlsx', '.xls', '.csv')):
            return Response({'detail': 'Only Excel (.xlsx, .xls) or CSV files are supported.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save file temporarily
        import os
        from django.conf import settings
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'bulk_uploads')
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file.name)

        with open(file_path, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        job = BulkUploadJob.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            file_name=file.name,
            file_url=file_path,
        )

        log_audit(request, 'bulk_upload_started', 'bulk_job', str(job.id), {'file_name': file.name})

        # Process synchronously (no Celery on PythonAnywhere)
        process_bulk_upload(str(job.id))
        job.refresh_from_db()

        return Response(BulkUploadJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BulkUploadJobStatusView(generics.RetrieveAPIView):
    """GET /api/v1/qr/bulk-upload/<id>/  Check bulk job status."""
    serializer_class = BulkUploadJobSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_queryset(self):
        return BulkUploadJob.objects.filter(organization=self.request.user.organization)


# 
# PASSWORD VERIFICATION (for protected QRs)
# 

class QRPasswordVerifyView(APIView):
    """POST /api/v1/qr/<id>/verify-password/  Public endpoint."""
    permission_classes = [permissions.AllowAny]

    _MAX_ATTEMPTS = 5      # wrong guesses before lockout
    _LOCKOUT_SECS = 300    # 5-minute lockout window

    def post(self, request, id):
        try:
            qr = QRCode.objects.get(id=id, is_password_protected=True)
        except QRCode.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        lockout_key  = f'qr_pw_lock:{id}'
        attempt_key  = f'qr_pw_try:{id}'

        if cache.get(lockout_key):
            return Response(
                {'detail': 'Too many incorrect attempts. Try again in 5 minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={'Retry-After': str(self._LOCKOUT_SECS)},
            )

        password = request.data.get('password', '')
        import bcrypt
        if bcrypt.checkpw(password.encode(), qr.password_hash.encode()):
            cache.delete(attempt_key)   # reset counter on success
            return Response({'verified': True, 'destination_url': qr.destination_url})

        # Wrong password — increment counter and maybe lock out
        log_audit(request, 'password_attempt_failed', 'qr_code', str(qr.id))
        try:
            attempts = cache.incr(attempt_key)
        except ValueError:
            cache.set(attempt_key, 1, timeout=self._LOCKOUT_SECS)
            attempts = 1
        if attempts >= self._MAX_ATTEMPTS:
            cache.set(lockout_key, True, timeout=self._LOCKOUT_SECS)
            cache.delete(attempt_key)
        return Response({'verified': False, 'detail': 'Incorrect password.'}, status=status.HTTP_403_FORBIDDEN)


# 
# VERSION HISTORY
# 

class QRVersionListView(generics.ListAPIView):
    """GET /api/v1/qr/<qr_id>/versions/  Version history."""
    serializer_class = QRVersionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    pagination_class = None

    def get_queryset(self):
        qr = _get_qr_with_access(self.request, self.kwargs['qr_id'])
        if not qr:
            return QRVersion.objects.none()
        return QRVersion.objects.filter(qr_code=qr)


class QRVersionRestoreView(APIView):
    """POST /api/v1/qr/<qr_id>/versions/<version_id>/restore/  Restore to version."""
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def post(self, request, qr_id, version_id):
        try:
            qr = _get_qr_with_access(request, qr_id)
            if not qr:
                return Response({'detail': 'Version not found.'}, status=status.HTTP_404_NOT_FOUND)
            version = QRVersion.objects.get(
                id=version_id,
                qr_code=qr,
            )
        except QRVersion.DoesNotExist:
            return Response({'detail': 'Version not found.'}, status=status.HTTP_404_NOT_FOUND)

        qr = version.qr_code
        snapshot = version.snapshot

        # Restore fields from snapshot
        restore_fields = [
            'title', 'description', 'destination_url', 'fallback_url',
            'qr_type', 'status', 'is_dynamic', 'static_content',
            'foreground_color', 'background_color', 'logo_url', 'error_correction',
            'module_style', 'gradient_type', 'gradient_start_color', 'gradient_end_color',
            'frame_style', 'frame_color', 'frame_text', 'frame_text_color',
            'is_password_protected', 'expires_at', 'scan_limit',
            'tags', 'metadata', 'folder',
        ]
        for field in restore_fields:
            if field in snapshot:
                setattr(qr, field, snapshot[field])

        qr.current_version += 1
        qr.save()

        QRVersion.objects.create(
            qr_code=qr,
            version_number=qr.current_version,
            snapshot=json.loads(json.dumps(QRCodeDetailSerializer(qr).data, default=str)),
            changed_by=request.user,
            change_summary=f'Restored to version {version.version_number}',
        )

        log_audit(request, 'qr_version_restored', 'qr_code', str(qr.id), {
            'restored_version': version.version_number,
        })

        return Response(QRCodeDetailSerializer(qr).data)


# 
# FEATURE 6  AUTO-ROTATING LANDING PAGES
# 

class RotationScheduleView(APIView):
    """
    GET    /api/v1/qr/<id>/rotation/    Get current schedule (404 if none)
    PUT    /api/v1/qr/<id>/rotation/    Create or fully replace schedule
    PATCH  /api/v1/qr/<id>/rotation/    Partial update
    DELETE /api/v1/qr/<id>/rotation/    Remove schedule
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            sched = qr.rotation_schedule
        except RotationSchedule.DoesNotExist:
            return Response({'detail': 'No rotation schedule set.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(RotationScheduleSerializer(sched).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            sched = qr.rotation_schedule
            serializer = RotationScheduleSerializer(sched, data=request.data)
        except RotationSchedule.DoesNotExist:
            serializer = RotationScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sched = serializer.save(qr_code=qr)
        # Invalidate redirect cache so rotation changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'rotation_saved', 'qr_code', str(qr.id), {
            'rotation_type': sched.rotation_type, 'pages': len(sched.pages),
        })
        return Response(RotationScheduleSerializer(sched).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            sched = qr.rotation_schedule
        except RotationSchedule.DoesNotExist:
            return Response({'detail': 'No rotation schedule. Use PUT to create one.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RotationScheduleSerializer(sched, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sched = serializer.save()
        # Invalidate redirect cache so rotation changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(RotationScheduleSerializer(sched).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.rotation_schedule.delete()
        except RotationSchedule.DoesNotExist:
            pass
        # Invalidate redirect cache so rotation removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'rotation_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# TIME-BASED REDIRECTS (Feature 9)
# 

class TimeScheduleView(APIView):
    """
    GET    /api/v1/qr/<id>/time-rules/    Get current time schedule (404 if none)
    PUT    /api/v1/qr/<id>/time-rules/    Create or fully replace time schedule
    PATCH  /api/v1/qr/<id>/time-rules/    Partial update
    DELETE /api/v1/qr/<id>/time-rules/    Remove time schedule
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            sched = qr.time_schedule
        except TimeSchedule.DoesNotExist:
            return Response({'detail': 'No time schedule set.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TimeScheduleSerializer(sched).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            sched = qr.time_schedule
            serializer = TimeScheduleSerializer(sched, data=request.data)
        except TimeSchedule.DoesNotExist:
            serializer = TimeScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sched = serializer.save(qr_code=qr)
        # Invalidate redirect cache so time schedule changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'time_schedule_saved', 'qr_code', str(qr.id), {
            'rules_count': len(sched.rules), 'tz': sched.tz,
        })
        return Response(TimeScheduleSerializer(sched).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            sched = qr.time_schedule
        except TimeSchedule.DoesNotExist:
            return Response({'detail': 'No time schedule. Use PUT to create one.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TimeScheduleSerializer(sched, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sched = serializer.save()
        # Invalidate redirect cache so time schedule changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(TimeScheduleSerializer(sched).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.time_schedule.delete()
        except TimeSchedule.DoesNotExist:
            pass
        # Invalidate redirect cache so time schedule removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'time_schedule_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# LANGUAGE ROUTE (Feature 8)
# 

class LanguageRouteView(APIView):
    """
    GET    /api/v1/qr/<id>/languages/    Get current language route (404 if none)
    PUT    /api/v1/qr/<id>/languages/    Create or fully replace language route
    DELETE /api/v1/qr/<id>/languages/    Remove language route
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            lang_route = qr.language_route
        except LanguageRoute.DoesNotExist:
            return Response({'detail': 'No language route configured.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(LanguageRouteSerializer(lang_route).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            lang_route = qr.language_route
            serializer = LanguageRouteSerializer(lang_route, data=request.data)
        except LanguageRoute.DoesNotExist:
            serializer = LanguageRouteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lang_route = serializer.save(qr_code=qr)
        # Invalidate redirect cache so language route changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'language_route_saved', 'qr_code', str(qr.id), {
            'routes_count': len(lang_route.routes),
            'geo_fallback_count': len(lang_route.geo_fallback or {}),
        })
        return Response(LanguageRouteSerializer(lang_route).data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.language_route.delete()
        except LanguageRoute.DoesNotExist:
            pass
        # Invalidate redirect cache so language route removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'language_route_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# PDF DOCUMENT (Feature 11  Inline PDF Viewer)
# 

class PDFDocumentView(APIView):
    """
    GET    /api/v1/qr/<id>/pdf/    Get PDF document metadata (404 if none)
    POST   /api/v1/qr/<id>/pdf/    Upload a PDF (creates/replaces)
    PATCH  /api/v1/qr/<id>/pdf/    Update settings (title, allow_download, is_active)
    DELETE /api/v1/qr/<id>/pdf/    Remove PDF document
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            pdf_doc = qr.pdf_document
        except PDFDocument.DoesNotExist:
            return Response({'detail': 'No PDF document configured.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PDFDocumentSerializer(pdf_doc).data)

    def post(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen

        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate it's a PDF by magic bytes — not the browser-supplied Content-Type
        if not _check_pdf_magic(file):
            return Response({'detail': 'Only PDF files are accepted.'}, status=status.HTTP_400_BAD_REQUEST)

        # Max 50MB
        max_size = 50 * 1024 * 1024
        if file.size > max_size:
            return Response(
                {'detail': f'File too large ({file.size / (1024*1024):.1f} MB). Maximum is 50 MB.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save to disk
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'pdf_files', str(qr.id))
        os.makedirs(upload_dir, exist_ok=True)

        # Clean old file if replacing
        try:
            old_doc = qr.pdf_document
            old_path = os.path.join(settings.MEDIA_ROOT, old_doc.file_path)
            if os.path.isfile(old_path):
                os.remove(old_path)
            old_doc.delete()
        except PDFDocument.DoesNotExist:
            pass

        # Save new file — use basename only to prevent path traversal
        safe_name = _sanitize_filename(file.name)
        if not safe_name.lower().endswith('.pdf'):
            safe_name += '.pdf'
        file_path_on_disk = os.path.join(upload_dir, safe_name)
        with open(file_path_on_disk, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        relative_path = f"pdf_files/{qr.id}/{safe_name}"

        # Try to get page count
        page_count = 0
        try:
            import subprocess
            # Attempt with PyPDF2 or pypdf if available
            try:
                from pypdf import PdfReader
                reader = PdfReader(file_path_on_disk)
                page_count = len(reader.pages)
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_path_on_disk)
                    page_count = len(reader.pages)
                except ImportError:
                    pass  # No PDF library available, page count stays 0
        except Exception:
            pass

        # Create PDFDocument
        pdf_doc = PDFDocument.objects.create(
            qr_code=qr,
            original_filename=file.name,
            file_path=relative_path,
            file_size=file.size,
            mime_type=file.content_type or 'application/pdf',
            page_count=page_count,
            title=request.data.get('title', '') or file.name.rsplit('.', 1)[0],
            allow_download=request.data.get('allow_download', 'false').lower() in ('true', '1', 'yes'),
            uploaded_by=request.user,
        )

        log_audit(request, 'pdf_uploaded', 'pdf_document', str(pdf_doc.id), {
            'qr_id': str(qr.id), 'filename': file.name, 'size': file.size,
        })

        return Response(PDFDocumentSerializer(pdf_doc).data, status=status.HTTP_201_CREATED)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            pdf_doc = qr.pdf_document
        except PDFDocument.DoesNotExist:
            return Response({'detail': 'No PDF document configured.'}, status=status.HTTP_404_NOT_FOUND)

        # Updatable fields
        if 'title' in request.data:
            pdf_doc.title = request.data['title']
        if 'allow_download' in request.data:
            val = request.data['allow_download']
            pdf_doc.allow_download = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'is_active' in request.data:
            val = request.data['is_active']
            pdf_doc.is_active = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'regenerate_token' in request.data:
            pdf_doc.access_token = uuid.uuid4()

        pdf_doc.save()
        log_audit(request, 'pdf_updated', 'pdf_document', str(pdf_doc.id), {
            'qr_id': str(qr.id),
        })
        return Response(PDFDocumentSerializer(pdf_doc).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            pdf_doc = qr.pdf_document
            # Remove file from disk
            full_path = os.path.join(settings.MEDIA_ROOT, pdf_doc.file_path)
            if os.path.isfile(full_path):
                os.remove(full_path)
            pdf_doc.delete()
        except PDFDocument.DoesNotExist:
            pass
        log_audit(request, 'pdf_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


#  Video Document (Feature 13) 
ALLOWED_VIDEO_TYPES = {
    'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime',
    'video/x-msvideo', 'video/x-matroska',
}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv'}


class VideoDocumentView(APIView):
    """
    GET    /api/v1/qr/<id>/video/    Get video document metadata
    POST   /api/v1/qr/<id>/video/    Upload a video (creates/replaces)
    PATCH  /api/v1/qr/<id>/video/    Update settings (title, allow_download, autoplay, loop)
    DELETE /api/v1/qr/<id>/video/    Remove video document
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            video_doc = qr.video_document
        except VideoDocument.DoesNotExist:
            return Response({'is_configured': False}, status=status.HTTP_200_OK)
        return Response(VideoDocumentSerializer(video_doc).data)

    def post(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen

        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate video type — extension/content_type + magic byte safety check
        content_type = (file.content_type or '').lower()
        ext = os.path.splitext(file.name)[1].lower()
        if content_type not in ALLOWED_VIDEO_TYPES and ext not in ALLOWED_VIDEO_EXTENSIONS:
            return Response(
                {'detail': f'Unsupported video format. Accepted: MP4, WebM, OGG, MOV, AVI, MKV.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Max 500MB
        max_size = 500 * 1024 * 1024
        if file.size > max_size:
            return Response(
                {'detail': f'File too large ({file.size / (1024*1024):.1f} MB). Maximum is 500 MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _check_not_dangerous(file):
            return Response({'detail': 'File content is not allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save to disk
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'video_files', str(qr.id))
        os.makedirs(upload_dir, exist_ok=True)

        # Clean old file if replacing
        try:
            old_doc = qr.video_document
            old_path = os.path.join(settings.MEDIA_ROOT, old_doc.file_path)
            if os.path.isfile(old_path):
                os.remove(old_path)
            # Remove old thumbnail too
            if old_doc.thumbnail_path:
                old_thumb = os.path.join(settings.MEDIA_ROOT, old_doc.thumbnail_path)
                if os.path.isfile(old_thumb):
                    os.remove(old_thumb)
            old_doc.delete()
        except VideoDocument.DoesNotExist:
            pass

        # Save new file — use basename only to prevent path traversal
        safe_name = _sanitize_filename(file.name)
        file_path_on_disk = os.path.join(upload_dir, safe_name)
        with open(file_path_on_disk, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        relative_path = f"video_files/{qr.id}/{safe_name}"

        # Determine mime type
        mime = content_type if content_type in ALLOWED_VIDEO_TYPES else 'video/mp4'

        # Try to get duration via ffprobe if available
        duration = 0.0
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', file_path_on_disk],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
        except Exception:
            pass  # ffprobe not available, duration stays 0

        # Parse boolean fields from multipart form
        allow_dl = request.data.get('allow_download', 'false')
        if isinstance(allow_dl, bool):
            allow_download = allow_dl
        else:
            allow_download = str(allow_dl).lower() in ('true', '1', 'yes')

        autoplay_val = request.data.get('autoplay', 'false')
        if isinstance(autoplay_val, bool):
            autoplay = autoplay_val
        else:
            autoplay = str(autoplay_val).lower() in ('true', '1', 'yes')

        loop_val = request.data.get('loop', 'false')
        if isinstance(loop_val, bool):
            loop = loop_val
        else:
            loop = str(loop_val).lower() in ('true', '1', 'yes')

        video_doc = VideoDocument.objects.create(
            qr_code=qr,
            original_filename=file.name,
            file_path=relative_path,
            file_size=file.size,
            mime_type=mime,
            duration_seconds=duration,
            title=request.data.get('title', '') or file.name.rsplit('.', 1)[0],
            allow_download=allow_download,
            autoplay=autoplay,
            loop=loop,
            uploaded_by=request.user,
        )

        log_audit(request, 'video_uploaded', 'video_document', str(video_doc.id), {
            'qr_id': str(qr.id), 'filename': file.name, 'size': file.size,
        })

        return Response(VideoDocumentSerializer(video_doc).data, status=status.HTTP_201_CREATED)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            video_doc = qr.video_document
        except VideoDocument.DoesNotExist:
            return Response({'detail': 'No video configured.'}, status=status.HTTP_404_NOT_FOUND)

        if 'title' in request.data:
            video_doc.title = request.data['title']
        if 'allow_download' in request.data:
            val = request.data['allow_download']
            video_doc.allow_download = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'autoplay' in request.data:
            val = request.data['autoplay']
            video_doc.autoplay = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'loop' in request.data:
            val = request.data['loop']
            video_doc.loop = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'is_active' in request.data:
            val = request.data['is_active']
            video_doc.is_active = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
        if 'regenerate_token' in request.data:
            video_doc.access_token = uuid.uuid4()

        video_doc.save()
        log_audit(request, 'video_updated', 'video_document', str(video_doc.id), {
            'qr_id': str(qr.id),
        })
        return Response(VideoDocumentSerializer(video_doc).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            video_doc = qr.video_document
            full_path = os.path.join(settings.MEDIA_ROOT, video_doc.file_path)
            if os.path.isfile(full_path):
                os.remove(full_path)
            if video_doc.thumbnail_path:
                thumb_path = os.path.join(settings.MEDIA_ROOT, video_doc.thumbnail_path)
                if os.path.isfile(thumb_path):
                    os.remove(thumb_path)
            video_doc.delete()
        except VideoDocument.DoesNotExist:
            pass
        log_audit(request, 'video_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# DEVICE ROUTE (Feature 15)
# 

class DeviceRouteView(APIView):
    """
    GET    /api/v1/qr/<id>/device-routes/    Get current device route config (404 if none)
    PUT    /api/v1/qr/<id>/device-routes/    Create or fully replace device route
    PATCH  /api/v1/qr/<id>/device-routes/    Partial update
    DELETE /api/v1/qr/<id>/device-routes/    Remove device route
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            route = qr.device_route
        except DeviceRoute.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(DeviceRouteSerializer(route).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            route = qr.device_route
            serializer = DeviceRouteSerializer(route, data=request.data)
        except DeviceRoute.DoesNotExist:
            serializer = DeviceRouteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        route = serializer.save(qr_code=qr)
        # Invalidate redirect cache so device route changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'device_route_saved', 'qr_code', str(qr.id), {
            'platforms_configured': sum(1 for f in [
                route.android_url, route.ios_url, route.windows_url,
                route.mac_url, route.tablet_url,
            ] if f),
        })
        return Response(DeviceRouteSerializer(route).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            route = qr.device_route
        except DeviceRoute.DoesNotExist:
            return Response(
                {'detail': 'No device route. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DeviceRouteSerializer(route, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        route = serializer.save()
        # Invalidate redirect cache so device route changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(DeviceRouteSerializer(route).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.device_route.delete()
        except DeviceRoute.DoesNotExist:
            pass
        # Invalidate redirect cache so device route removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'device_route_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# GEO-FENCE RULE (Feature 17)
# 

class GeoFenceRuleView(APIView):
    """
    GET    /api/v1/qr/<id>/geo-fence/    Get current geo-fence config (404 if none)
    PUT    /api/v1/qr/<id>/geo-fence/    Create or fully replace geo-fence
    PATCH  /api/v1/qr/<id>/geo-fence/    Partial update
    DELETE /api/v1/qr/<id>/geo-fence/    Remove geo-fence
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            fence = qr.geo_fence
        except GeoFenceRule.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(GeoFenceRuleSerializer(fence).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            fence = qr.geo_fence
            serializer = GeoFenceRuleSerializer(fence, data=request.data)
        except GeoFenceRule.DoesNotExist:
            serializer = GeoFenceRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fence = serializer.save(qr_code=qr)
        # Invalidate redirect cache so geo fence changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'geo_fence_saved', 'qr_code', str(qr.id), {
            'zones_count': len(fence.zones) if fence.zones else 0,
        })
        return Response(GeoFenceRuleSerializer(fence).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            fence = qr.geo_fence
        except GeoFenceRule.DoesNotExist:
            return Response(
                {'detail': 'No geo-fence. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = GeoFenceRuleSerializer(fence, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fence = serializer.save()
        # Invalidate redirect cache so geo fence changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(GeoFenceRuleSerializer(fence).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.geo_fence.delete()
        except GeoFenceRule.DoesNotExist:
            pass
        # Invalidate redirect cache so geo fence removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'geo_fence_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# A/B SPLIT TEST (Feature 18)
# 

class ABTestView(APIView):
    """
    GET    /api/v1/qr/<id>/ab-test/    Get current A/B test config (404 if none)
    PUT    /api/v1/qr/<id>/ab-test/    Create or fully replace A/B test
    PATCH  /api/v1/qr/<id>/ab-test/    Partial update
    DELETE /api/v1/qr/<id>/ab-test/    Remove A/B test
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            ab = qr.ab_test
        except ABTest.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(ABTestSerializer(ab).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            ab = qr.ab_test
            serializer = ABTestSerializer(ab, data=request.data)
        except ABTest.DoesNotExist:
            serializer = ABTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ab = serializer.save(qr_code=qr)
        # Invalidate redirect cache so AB test changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'ab_test_saved', 'qr_code', str(qr.id), {
            'variants_count': len(ab.variants) if ab.variants else 0,
        })
        return Response(ABTestSerializer(ab).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            ab = qr.ab_test
        except ABTest.DoesNotExist:
            return Response(
                {'detail': 'No A/B test. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ABTestSerializer(ab, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ab = serializer.save()
        # Invalidate redirect cache so AB test changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(ABTestSerializer(ab).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.ab_test.delete()
        except ABTest.DoesNotExist:
            pass
        # Invalidate redirect cache so AB test removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'ab_test_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# APP DEEP LINK (Feature 19)
# 

class DeepLinkView(APIView):
    """
    GET    /api/v1/qr/<id>/deep-link/    Get current deep link config (404 if none)
    PUT    /api/v1/qr/<id>/deep-link/    Create or fully replace deep link
    PATCH  /api/v1/qr/<id>/deep-link/    Partial update
    DELETE /api/v1/qr/<id>/deep-link/    Remove deep link
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            dl = qr.deep_link
        except DeepLink.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(DeepLinkSerializer(dl).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            dl = qr.deep_link
            serializer = DeepLinkSerializer(dl, data=request.data)
        except DeepLink.DoesNotExist:
            serializer = DeepLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dl = serializer.save(qr_code=qr)
        # Invalidate redirect cache so deep link changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'deep_link_saved', 'qr_code', str(qr.id))
        return Response(DeepLinkSerializer(dl).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            dl = qr.deep_link
        except DeepLink.DoesNotExist:
            return Response(
                {'detail': 'No deep link. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DeepLinkSerializer(dl, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        dl = serializer.save()
        # Invalidate redirect cache so deep link changes take effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        return Response(DeepLinkSerializer(dl).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.deep_link.delete()
        except DeepLink.DoesNotExist:
            pass
        # Invalidate redirect cache so deep link removal takes effect immediately
        cache.delete(f"qr:obj:{qr.slug}")
        log_audit(request, 'deep_link_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# TOKEN REDIRECT (Feature 20)
# 
class TokenRedirectView(APIView):
    """
    Short-Lived Token Redirect config for a QR code.

    GET    /api/v1/qr/<id>/token-redirect/    Retrieve config
    PUT    /api/v1/qr/<id>/token-redirect/    Create or replace config
    PATCH  /api/v1/qr/<id>/token-redirect/    Partial update
    DELETE /api/v1/qr/<id>/token-redirect/    Remove config
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            tr = qr.token_redirect
        except TokenRedirect.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(TokenRedirectSerializer(tr).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            tr = qr.token_redirect
            serializer = TokenRedirectSerializer(tr, data=request.data)
        except TokenRedirect.DoesNotExist:
            serializer = TokenRedirectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tr = serializer.save(qr_code=qr)
        log_audit(request, 'token_redirect_saved', 'qr_code', str(qr.id))
        return Response(TokenRedirectSerializer(tr).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            tr = qr.token_redirect
        except TokenRedirect.DoesNotExist:
            return Response(
                {'detail': 'No token redirect. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TokenRedirectSerializer(tr, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tr = serializer.save()
        return Response(TokenRedirectSerializer(tr).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.token_redirect.delete()
        except TokenRedirect.DoesNotExist:
            pass
        log_audit(request, 'token_redirect_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# EXPIRY-BASED QR (Feature 21)
# 
class QRExpiryView(APIView):
    """
    Expiry configuration for a QR code.

    GET    /api/v1/qr/<id>/expiry/    Retrieve config
    PUT    /api/v1/qr/<id>/expiry/    Create or replace config
    PATCH  /api/v1/qr/<id>/expiry/    Partial update
    DELETE /api/v1/qr/<id>/expiry/    Remove config
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            exp = qr.expiry
        except QRExpiry.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        data = QRExpirySerializer(exp).data
        data['is_expired'] = exp.is_expired()
        return Response(data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            exp = qr.expiry
            serializer = QRExpirySerializer(exp, data=request.data)
        except QRExpiry.DoesNotExist:
            serializer = QRExpirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exp = serializer.save(qr_code=qr)
        log_audit(request, 'expiry_saved', 'qr_code', str(qr.id))
        data = QRExpirySerializer(exp).data
        data['is_expired'] = exp.is_expired()
        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            exp = qr.expiry
        except QRExpiry.DoesNotExist:
            return Response(
                {'detail': 'No expiry config. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = QRExpirySerializer(exp, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        exp = serializer.save()
        data = QRExpirySerializer(exp).data
        data['is_expired'] = exp.is_expired()
        return Response(data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.expiry.delete()
        except QRExpiry.DoesNotExist:
            pass
        log_audit(request, 'expiry_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


#  Scan Alerts (Feature 25) 
class ScanAlertView(APIView):
    """
    Scan-alert configuration for a QR code.

    GET    /api/v1/qr/<id>/scan-alert/    Retrieve config
    PUT    /api/v1/qr/<id>/scan-alert/    Create or replace config
    PATCH  /api/v1/qr/<id>/scan-alert/    Partial update
    DELETE /api/v1/qr/<id>/scan-alert/    Remove config
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            alert = qr.scan_alert
        except ScanAlert.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(ScanAlertSerializer(alert).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            alert = qr.scan_alert
            serializer = ScanAlertSerializer(alert, data=request.data)
        except ScanAlert.DoesNotExist:
            serializer = ScanAlertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = serializer.save(qr_code=qr)
        log_audit(request, 'scan_alert_saved', 'qr_code', str(qr.id))
        return Response(ScanAlertSerializer(alert).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            alert = qr.scan_alert
        except ScanAlert.DoesNotExist:
            return Response(
                {'detail': 'No scan alert config. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ScanAlertSerializer(alert, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        alert = serializer.save()
        return Response(ScanAlertSerializer(alert).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.scan_alert.delete()
        except ScanAlert.DoesNotExist:
            pass
        log_audit(request, 'scan_alert_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


#  Loyalty Point QR (Feature 26) 
class LoyaltyProgramView(APIView):
    """
    Loyalty program configuration for a QR code.

    GET    /api/v1/qr/<id>/loyalty/    Retrieve config + members
    PUT    /api/v1/qr/<id>/loyalty/    Create or replace config
    PATCH  /api/v1/qr/<id>/loyalty/    Partial update
    DELETE /api/v1/qr/<id>/loyalty/    Remove config
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_qr(self, request, id):
        return _get_qr_with_access(request, id)

    def get(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            prog = qr.loyalty_program
        except LoyaltyProgram.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(LoyaltyProgramSerializer(prog).data)

    def put(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            prog = qr.loyalty_program
            serializer = LoyaltyProgramSerializer(prog, data=request.data)
        except LoyaltyProgram.DoesNotExist:
            serializer = LoyaltyProgramSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prog = serializer.save(qr_code=qr)
        log_audit(request, 'loyalty_saved', 'qr_code', str(qr.id))
        return Response(LoyaltyProgramSerializer(prog).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            prog = qr.loyalty_program
        except LoyaltyProgram.DoesNotExist:
            return Response(
                {'detail': 'No loyalty program. Use PUT to create one.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = LoyaltyProgramSerializer(prog, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prog = serializer.save()
        return Response(LoyaltyProgramSerializer(prog).data)

    def delete(self, request, id):
        qr = self._get_qr(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        try:
            qr.loyalty_program.delete()
        except LoyaltyProgram.DoesNotExist:
            pass
        log_audit(request, 'loyalty_deleted', 'qr_code', str(qr.id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoyaltyMembersView(APIView):
    """
    List members of a loyalty program or add/adjust a member manually.

    GET    /api/v1/qr/<id>/loyalty/members/    List all members
    POST   /api/v1/qr/<id>/loyalty/members/    Add points manually
    DELETE /api/v1/qr/<id>/loyalty/members/     Remove member by identifier
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgEditor]

    def _get_program(self, request, id):
        try:
            qr = _get_qr_with_access(request, id)
            if not qr:
                return None
            return qr.loyalty_program
        except LoyaltyProgram.DoesNotExist:
            return None

    def get(self, request, id):
        prog = self._get_program(request, id)
        if not prog:
            return Response({'detail': 'Loyalty program not found.'}, status=status.HTTP_404_NOT_FOUND)
        members = prog.members.all()
        return Response(LoyaltyMemberSerializer(members, many=True).data)

    def post(self, request, id):
        """Manually add points to a member."""
        prog = self._get_program(request, id)
        if not prog:
            return Response({'detail': 'Loyalty program not found.'}, status=status.HTTP_404_NOT_FOUND)
        identifier = request.data.get('identifier', '').strip()
        points = int(request.data.get('points', 0))
        name = request.data.get('name', '')
        if not identifier:
            return Response({'detail': 'identifier is required.'}, status=status.HTTP_400_BAD_REQUEST)
        member, created = LoyaltyMember.objects.get_or_create(
            program=prog, identifier=identifier,
            defaults={'name': name},
        )
        member.points += points
        member.total_scans += 1
        member.last_scan_at = timezone.now()
        if name and not member.name:
            member.name = name
        member.save()
        if created:
            LoyaltyProgram.objects.filter(pk=prog.pk).update(
                total_members=DBF('total_members') + 1
            )
        LoyaltyProgram.objects.filter(pk=prog.pk).update(
            total_points_issued=DBF('total_points_issued') + points
        )
        return Response(LoyaltyMemberSerializer(member).data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        prog = self._get_program(request, id)
        if not prog:
            return Response({'detail': 'Loyalty program not found.'}, status=status.HTTP_404_NOT_FOUND)
        identifier = request.data.get('identifier', '').strip()
        if not identifier:
            return Response({'detail': 'identifier is required.'}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = LoyaltyMember.objects.filter(program=prog, identifier=identifier).delete()
        if deleted:
            LoyaltyProgram.objects.filter(pk=prog.pk).update(
                total_members=DBF('total_members') - 1
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoyaltyScanView(APIView):
    """
    Public endpoint  called when someone scans a loyalty QR.
    No auth required (scanner is public).

    POST /api/v1/qr/<id>/loyalty/scan/
    Body: { identifier, name? }
    """
    permission_classes = []
    authentication_classes = []

    def post(self, request, id):
        try:
            prog = LoyaltyProgram.objects.select_related('qr_code').get(
                qr_code_id=id, is_active=True,
            )
        except LoyaltyProgram.DoesNotExist:
            return Response({'detail': 'No active loyalty program.'}, status=status.HTTP_404_NOT_FOUND)

        identifier = request.data.get('identifier', '').strip()
        name = request.data.get('name', '').strip()
        if not identifier:
            return Response({'detail': 'Email or phone number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        member, created = LoyaltyMember.objects.get_or_create(
            program=prog, identifier=identifier,
            defaults={'name': name},
        )

        now = timezone.now()
        points_to_add = prog.points_per_scan

        # Daily cap check
        if prog.max_points_per_day > 0 and member.last_scan_at:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if member.last_scan_at >= today_start:
                # Calculate today's earned points (approximate by scan count today * points_per_scan)
                from django.db.models import Sum
                today_scans = LoyaltyMember.objects.filter(
                    pk=member.pk, last_scan_at__gte=today_start
                ).count()
                estimated_today = member.total_scans * prog.points_per_scan if today_scans else 0
                # Simplified: just check if we'd exceed max
                if estimated_today >= prog.max_points_per_day:
                    return Response({
                        'detail': 'Daily points limit reached. Come back tomorrow!',
                        'points': member.points,
                        'total_scans': member.total_scans,
                        'daily_limit_reached': True,
                    }, status=status.HTTP_200_OK)

        # Bonus points on first scan
        if created and prog.bonus_points > 0:
            points_to_add += prog.bonus_points

        member.points += points_to_add
        member.total_scans += 1
        member.last_scan_at = now
        if name and not member.name:
            member.name = name
        member.save()

        if created:
            LoyaltyProgram.objects.filter(pk=prog.pk).update(
                total_members=DBF('total_members') + 1
            )
        LoyaltyProgram.objects.filter(pk=prog.pk).update(
            total_points_issued=DBF('total_points_issued') + points_to_add
        )

        # Determine earned rewards
        earned_tiers = []
        for tier in (prog.reward_tiers or []):
            if member.points >= tier.get('points_required', 0):
                earned_tiers.append(tier)

        # Next reward
        next_tier = None
        for tier in sorted(prog.reward_tiers or [], key=lambda t: t.get('points_required', 0)):
            if member.points < tier.get('points_required', 0):
                next_tier = tier
                break

        return Response({
            'program_name': prog.program_name,
            'points_earned': points_to_add,
            'total_points': member.points,
            'total_scans': member.total_scans,
            'earned_rewards': earned_tiers,
            'next_reward': next_tier,
            'is_new_member': created,
        })


#  Digital vCard Views (Feature 28) 
class DigitalVCardView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET / PUT / PATCH / DELETE the digital vCard config for a QR code.
    PUT also handles creation (upsert).
    """
    serializer_class = DigitalVCardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        try:
            return qr.vcard
        except DigitalVCard.DoesNotExist:
            return None

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({}, status=status.HTTP_200_OK)
        return Response(self.get_serializer(instance).data)

    def put(self, request, *args, **kwargs):
        """Upsert  create if missing, update if exists."""
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        try:
            instance = qr.vcard
            serializer = self.get_serializer(instance, data=request.data)
        except DigitalVCard.DoesNotExist:
            serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(qr_code=qr)
        return Response(serializer.data, status=status.HTTP_200_OK)


class VCardDownloadView(APIView):
    """Public endpoint  returns a .vcf file for the given QR's vCard."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, id):
        qr = get_object_or_404(QRCode, id=id)
        try:
            vc = qr.vcard
        except DigitalVCard.DoesNotExist:
            raise Http404('No vCard configured.')
        if not vc.is_active:
            raise Http404('vCard is disabled.')

        # Build VCF manually (no vobject dependency needed)
        lines = [
            'BEGIN:VCARD',
            'VERSION:3.0',
            f'N:{vc.last_name};{vc.first_name};;;',
            f'FN:{vc.full_name()}',
        ]
        if vc.organization:
            lines.append(f'ORG:{vc.organization}')
        if vc.title:
            lines.append(f'TITLE:{vc.title}')
        if vc.department:
            lines.append(f'X-DEPARTMENT:{vc.department}')
        if vc.email:
            lines.append(f'EMAIL;TYPE=HOME:{vc.email}')
        if vc.email_work:
            lines.append(f'EMAIL;TYPE=WORK:{vc.email_work}')
        if vc.phone:
            lines.append(f'TEL;TYPE=HOME:{vc.phone}')
        if vc.phone_work:
            lines.append(f'TEL;TYPE=WORK:{vc.phone_work}')
        if vc.phone_cell:
            lines.append(f'TEL;TYPE=CELL:{vc.phone_cell}')
        if vc.website:
            lines.append(f'URL:{vc.website}')
        if vc.linkedin:
            lines.append(f'X-SOCIALPROFILE;TYPE=linkedin:{vc.linkedin}')
        if vc.twitter:
            lines.append(f'X-SOCIALPROFILE;TYPE=twitter:https://twitter.com/{vc.twitter.lstrip("@")}')
        if vc.github:
            lines.append(f'X-SOCIALPROFILE;TYPE=github:{vc.github}')
        if vc.instagram:
            lines.append(f'X-SOCIALPROFILE;TYPE=instagram:https://instagram.com/{vc.instagram.lstrip("@")}')
        if any([vc.street, vc.city, vc.state, vc.zip_code, vc.country]):
            lines.append(f'ADR;TYPE=HOME:;;{vc.street};{vc.city};{vc.state};{vc.zip_code};{vc.country}')
        if vc.photo_url:
            lines.append(f'PHOTO;VALUE=URI:{vc.photo_url}')
        if vc.note:
            lines.append(f'NOTE:{vc.note}')
        if vc.bio:
            lines.append(f'X-BIO:{vc.bio}')
        lines.append('END:VCARD')

        vcf_text = '\r\n'.join(lines) + '\r\n'
        safe_name = vc.full_name().replace(' ', '_') or 'contact'
        response = HttpResponse(vcf_text, content_type='text/vcard; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{safe_name}.vcf"'
        return response


#  Product Authentication Views (Feature 31) 
class ProductAuthView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE product authentication config for a QR code. PUT upserts."""
    serializer_class = ProductAuthSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        try:
            return qr.product_auth
        except ProductAuth.DoesNotExist:
            return None

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({}, status=status.HTTP_200_OK)
        return Response(self.get_serializer(instance).data)

    def put(self, request, *args, **kwargs):
        """Upsert  create if missing, update if exists."""
        import secrets
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        data = request.data.copy()
        try:
            instance = qr.product_auth
            serializer = self.get_serializer(instance, data=data)
        except ProductAuth.DoesNotExist:
            # Auto-generate secret key if not provided
            if not data.get('secret_key'):
                data['secret_key'] = secrets.token_hex(32)
            serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(qr_code=qr)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductSerialListView(APIView):
    """GET serials list, DELETE a serial by serial_number."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            pa = qr.product_auth
        except ProductAuth.DoesNotExist:
            raise Http404('No product authentication configured.')
        serials = pa.serials.all()[:200]
        return Response(ProductSerialSerializer(serials, many=True).data)

    def delete(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            pa = qr.product_auth
        except ProductAuth.DoesNotExist:
            raise Http404('No product authentication configured.')
        serial_number = request.data.get('serial_number', '')
        deleted, _ = pa.serials.filter(serial_number=serial_number).delete()
        if deleted:
            return Response({'detail': 'Serial removed.'})
        return Response({'detail': 'Serial not found.'}, status=status.HTTP_404_NOT_FOUND)


class ProductSerialGenerateView(APIView):
    """POST  generate N serial numbers with HMAC signatures."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        import hmac, hashlib, secrets as _secrets
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            pa = qr.product_auth
        except ProductAuth.DoesNotExist:
            raise Http404('No product authentication configured.')

        count = min(int(request.data.get('count', 10)), 500)
        batch_label = request.data.get('batch_label', '')
        manufactured_date = request.data.get('manufactured_date', None)
        prefix = request.data.get('prefix', '')

        created = []
        for _ in range(count):
            serial = prefix + _secrets.token_hex(8).upper()
            sig = hmac.new(
                pa.secret_key.encode(),
                serial.encode(),
                hashlib.sha256
            ).hexdigest()
            obj = ProductSerial.objects.create(
                product_auth=pa,
                serial_number=serial,
                hmac_signature=sig,
                batch_label=batch_label,
                manufactured_date=manufactured_date if manufactured_date else None,
            )
            created.append(obj)

        return Response({
            'generated': len(created),
            'serials': ProductSerialSerializer(created, many=True).data,
        }, status=status.HTTP_201_CREATED)


class ProductVerifyView(APIView):
    """Public POST  verify a serial number. Logs scan."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, id):
        import hmac as _hmac, hashlib
        qr = get_object_or_404(QRCode, id=id)
        try:
            pa = qr.product_auth
        except ProductAuth.DoesNotExist:
            return Response({'authentic': False, 'reason': 'No authentication configured.'}, status=400)
        if not pa.is_active:
            return Response({'authentic': False, 'reason': 'Product authentication disabled.'}, status=400)

        serial_number = (request.data.get('serial') or '').strip()
        if not serial_number:
            return Response({'authentic': False, 'reason': 'Serial number required.'}, status=400)

        # Compute expected HMAC
        expected_sig = _hmac.new(
            pa.secret_key.encode(),
            serial_number.encode(),
            hashlib.sha256
        ).hexdigest()

        # Find serial
        try:
            serial_obj = pa.serials.get(serial_number=serial_number)
        except ProductSerial.DoesNotExist:
            return Response({
                'authentic': False,
                'reason': 'Serial number not found in our database.',
                'product_name': pa.product_name,
                'manufacturer': pa.manufacturer,
            })

        # Verify HMAC
        is_valid = _hmac.compare_digest(serial_obj.hmac_signature, expected_sig)

        # Log scan
        from django.utils import timezone as _tz
        now = _tz.now()
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        serial_obj.total_scans += 1
        serial_obj.last_scanned_at = now
        serial_obj.last_scanned_ip = client_ip or None
        if not serial_obj.first_scanned_at:
            serial_obj.first_scanned_at = now
        if is_valid and serial_obj.status == 'unscanned':
            serial_obj.status = 'verified'
        elif not is_valid:
            serial_obj.status = 'flagged'
        serial_obj.save()

        return Response({
            'authentic': is_valid,
            'reason': 'Product is authentic!' if is_valid else 'HMAC mismatch  possible counterfeit.',
            'product_name': pa.product_name,
            'manufacturer': pa.manufacturer,
            'product_image_url': pa.product_image_url,
            'serial_number': serial_number,
            'total_scans': serial_obj.total_scans,
            'first_scanned_at': serial_obj.first_scanned_at,
            'status': serial_obj.status,
            'support_url': pa.support_url,
            'support_email': pa.support_email,
        })


# 
# DOCUMENT UPLOAD FORM  (Feature 33)
# 

class DocUploadFormView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE document-upload form config for a QR code. PUT upserts."""
    serializer_class = DocumentUploadFormSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        try:
            return qr.doc_upload_form
        except DocumentUploadForm.DoesNotExist:
            return None

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({}, status=status.HTTP_200_OK)
        return Response(self.get_serializer(instance).data)

    def put(self, request, *args, **kwargs):
        """Upsert  create if missing, update if exists."""
        qr = _get_qr_with_access(self.request, self.kwargs['id'])
        if not qr:
            raise Http404("QR code not found.")
        data = request.data.copy()
        try:
            instance = qr.doc_upload_form
            serializer = self.get_serializer(instance, data=data)
        except DocumentUploadForm.DoesNotExist:
            serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(qr_code=qr)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocSubmissionsListView(APIView):
    """GET list of submissions, DELETE a submission by id."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            form = qr.doc_upload_form
        except DocumentUploadForm.DoesNotExist:
            raise Http404('No document upload form configured.')
        submissions = form.submissions.prefetch_related('files').all()[:200]
        return Response(DocumentSubmissionSerializer(submissions, many=True).data)

    def delete(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        sub_id = request.data.get('submission_id')
        if not sub_id:
            return Response({'detail': 'submission_id required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            form = qr.doc_upload_form
        except DocumentUploadForm.DoesNotExist:
            raise Http404
        sub = get_object_or_404(DocumentSubmission, id=sub_id, form=form)
        # Delete physical files
        for f in sub.files.all():
            full = os.path.join(settings.MEDIA_ROOT, f.file_path)
            if os.path.isfile(full):
                os.remove(full)
        sub.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocPublicUploadView(APIView):
    """Public endpoint  lets anyone upload documents via multipart/form-data."""
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request, id):
        qr = get_object_or_404(QRCode, id=id)
        try:
            form = qr.doc_upload_form
        except DocumentUploadForm.DoesNotExist:
            return Response({'detail': 'Upload form not configured.'}, status=status.HTTP_404_NOT_FOUND)
        if not form.is_active:
            return Response({'detail': 'Upload form is disabled.'}, status=status.HTTP_403_FORBIDDEN)

        # Validate contact fields
        submitter_name = request.data.get('name', '').strip()
        submitter_email = request.data.get('email', '').strip()
        submitter_phone = request.data.get('phone', '').strip()
        notes = request.data.get('notes', '').strip()

        errors = {}
        if form.require_name and not submitter_name:
            errors['name'] = 'Name is required.'
        if form.require_email and not submitter_email:
            errors['email'] = 'Email is required.'
        if form.require_phone and not submitter_phone:
            errors['phone'] = 'Phone is required.'

        files = request.FILES.getlist('files')
        if not files:
            errors['files'] = 'At least one file is required.'
        if len(files) > form.max_files:
            errors['files'] = f'Maximum {form.max_files} files allowed.'
        if errors:
            return Response({'detail': errors}, status=status.HTTP_400_BAD_REQUEST)

        allowed_ext = [e.strip().lower() for e in form.allowed_extensions.split(',') if e.strip()]
        max_bytes = form.max_file_size_mb * 1024 * 1024

        # Validate each file
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if allowed_ext and ext not in allowed_ext:
                return Response({'detail': f'File type {ext} not allowed. Accepted: {form.allowed_extensions}'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not _check_not_dangerous(f):
                return Response({'detail': f'File "{f.name}" contains disallowed content.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if f.size > max_bytes:
                return Response({'detail': f'{f.name} exceeds {form.max_file_size_mb} MB limit.'},
                                status=status.HTTP_400_BAD_REQUEST)

        # Extract IP
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        # Create submission
        import mimetypes
        submission = DocumentSubmission.objects.create(
            form=form,
            submitter_name=submitter_name,
            submitter_email=submitter_email,
            submitter_phone=submitter_phone,
            ip_address=client_ip or None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            notes=notes,
        )

        upload_dir = os.path.join(settings.MEDIA_ROOT, 'doc_uploads', str(form.id), str(submission.id))
        os.makedirs(upload_dir, exist_ok=True)

        category = request.data.get('category', '')

        saved_files = []
        for f in files:
            safe_name = _sanitize_filename(f.name)
            dest = os.path.join(upload_dir, safe_name)
            with open(dest, 'wb+') as out:
                for chunk in f.chunks():
                    out.write(chunk)
            mt, _ = mimetypes.guess_type(f.name)
            doc_file = DocumentFile.objects.create(
                submission=submission,
                original_name=f.name,
                file_path=f'doc_uploads/{form.id}/{submission.id}/{safe_name}',
                file_size=f.size,
                mime_type=mt or 'application/octet-stream',
                category=category,
            )
            saved_files.append(doc_file.original_name)

        return Response({
            'success': True,
            'submission_id': str(submission.id),
            'files_saved': len(saved_files),
            'message': form.success_message or 'Documents uploaded successfully!',
        }, status=status.HTTP_201_CREATED)


# 
# FUNNEL PAGES (Feature 34)
# 

class FunnelConfigView(generics.GenericAPIView):
    """GET / PUT / PATCH / DELETE the funnel config for a QR code (upsert on PUT)."""
    serializer_class = FunnelConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            config = qr.funnel_config
        except FunnelConfig.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        return Response(FunnelConfigSerializer(config).data)

    def put(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        config, _ = FunnelConfig.objects.get_or_create(qr_code=qr)
        ser = FunnelConfigSerializer(config, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    patch = put

    def delete(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        frozen = _check_frozen(qr, request)
        if frozen:
            return frozen
        FunnelConfig.objects.filter(qr_code=qr).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FunnelStepListView(generics.GenericAPIView):
    """GET list steps / POST create step / DELETE by step_id query-param / PUT reorder."""
    serializer_class = FunnelStepSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_funnel(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return None
        try:
            return FunnelConfig.objects.get(qr_code=qr)
        except FunnelConfig.DoesNotExist:
            return None

    def get(self, request, id):
        funnel = self._get_funnel(request, id)
        if not funnel:
            return Response({'detail': 'Funnel not found.'}, status=status.HTTP_404_NOT_FOUND)
        steps = funnel.steps.all()
        return Response(FunnelStepSerializer(steps, many=True).data)

    def post(self, request, id):
        funnel = self._get_funnel(request, id)
        if not funnel:
            return Response({'detail': 'Funnel not found.'}, status=status.HTTP_404_NOT_FOUND)
        last_order = funnel.steps.count()
        data = request.data.copy()
        data['funnel'] = str(funnel.id)
        data.setdefault('step_order', last_order)
        ser = FunnelStepSerializer(data=data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)

    def put(self, request, id):
        """Reorder steps: expects { "order": ["uuid1","uuid2",...] }"""
        funnel = self._get_funnel(request, id)
        if not funnel:
            return Response({'detail': 'Funnel not found.'}, status=status.HTTP_404_NOT_FOUND)
        order = request.data.get('order', [])
        for idx, step_id in enumerate(order):
            FunnelStep.objects.filter(id=step_id, funnel=funnel).update(step_order=idx)
        return Response(FunnelStepSerializer(funnel.steps.all(), many=True).data)

    def patch(self, request, id):
        """Update a single step: expects step_id in body."""
        funnel = self._get_funnel(request, id)
        if not funnel:
            return Response({'detail': 'Funnel not found.'}, status=status.HTTP_404_NOT_FOUND)
        step_id = request.data.get('step_id')
        step = get_object_or_404(FunnelStep, id=step_id, funnel=funnel)
        ser = FunnelStepSerializer(step, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, id):
        funnel = self._get_funnel(request, id)
        if not funnel:
            return Response({'detail': 'Funnel not found.'}, status=status.HTTP_404_NOT_FOUND)
        step_id = request.query_params.get('step_id')
        if not step_id:
            return Response({'error': 'step_id required'}, status=status.HTTP_400_BAD_REQUEST)
        FunnelStep.objects.filter(id=step_id, funnel=funnel).delete()
        # re-order remaining
        for idx, step in enumerate(funnel.steps.all()):
            if step.step_order != idx:
                step.step_order = idx
                step.save(update_fields=['step_order'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class FunnelPublicView(APIView):
    """Public endpoint: GET funnel data for rendering the public page."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, id):
        config = get_object_or_404(FunnelConfig, qr_code_id=id, is_active=True)
        steps = config.steps.all()
        return Response({
            'title': config.title,
            'description': config.description,
            'brand_color': config.brand_color or '#6366f1',
            'show_progress_bar': config.show_progress_bar,
            'allow_back_navigation': config.allow_back_navigation,
            'steps': FunnelStepSerializer(steps, many=True).data,
        })


class FunnelTrackView(APIView):
    """Public endpoint: POST to track visitor progression through funnel."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, id):
        config = get_object_or_404(FunnelConfig, qr_code_id=id, is_active=True)
        session_key = request.data.get('session_key', '')
        current_step = request.data.get('current_step', 0)
        is_completed = request.data.get('is_completed', False)

        if not session_key:
            return Response({'error': 'session_key required'}, status=status.HTTP_400_BAD_REQUEST)

        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        client_ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')

        session, created = FunnelSession.objects.get_or_create(
            funnel=config,
            session_key=session_key,
            defaults={
                'ip_address': client_ip,
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
            }
        )
        session.current_step = current_step
        if is_completed and not session.is_completed:
            session.is_completed = True
            from django.utils import timezone
            session.completed_at = timezone.now()
        session.save()

        return Response({'ok': True, 'step': session.current_step, 'completed': session.is_completed})


class FunnelSessionsView(generics.GenericAPIView):
    """GET funnel sessions (analytics). Authenticated owner only."""
    serializer_class = FunnelSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)
        config = get_object_or_404(FunnelConfig, qr_code=qr)
        sessions = config.sessions.all()[:200]
        return Response(FunnelSessionSerializer(sessions, many=True).data)


# 
# ROLE-BASED QR ACCESS (Feature 36)
# 

ROLE_RANK = {'owner': 4, 'admin': 3, 'editor': 2, 'viewer': 1}


def _get_qr_for_role(request, qr_id, min_role='viewer'):
    """Return QR if user is owner (created_by) or has at least min_role via QRCodeAccess."""
    qr = get_object_or_404(QRCode, id=qr_id)
    if qr.created_by == request.user:
        return qr, 'owner'
    try:
        access = QRCodeAccess.objects.get(qr_code=qr, user=request.user)
        if ROLE_RANK.get(access.role, 0) >= ROLE_RANK.get(min_role, 0):
            return qr, access.role
    except QRCodeAccess.DoesNotExist:
        pass
    return None, None


class QRAccessListView(generics.GenericAPIView):
    """GET list access entries / POST invite user / PATCH update role / DELETE revoke."""
    serializer_class = QRCodeAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _require(self, request, id, min_role='admin'):
        qr, role = _get_qr_for_role(request, id, min_role)
        if not qr:
            return None, None, Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        return qr, role, None

    def get(self, request, id):
        qr, role, err = self._require(request, id, 'viewer')
        if err:
            return err
        entries = QRCodeAccess.objects.filter(qr_code=qr).select_related('user', 'granted_by')
        data = QRCodeAccessSerializer(entries, many=True).data
        # Prepend the owner (created_by) as a virtual entry
        owner = qr.created_by
        owner_entry = {
            'id': None,
            'qr_code': str(qr.id),
            'user': str(owner.id) if owner else None,
            'user_email': owner.email if owner else '',
            'user_name': f"{owner.first_name} {owner.last_name}".strip() or owner.email if owner else '',
            'role': 'owner',
            'granted_by': None,
            'granted_by_email': None,
            'created_at': qr.created_at.isoformat() if hasattr(qr, 'created_at') else None,
            'updated_at': None,
        }
        return Response([owner_entry] + data)

    def post(self, request, id):
        """Invite: body = { email, role }"""
        qr, caller_role, err = self._require(request, id, 'admin')
        if err:
            return err
        email = request.data.get('email', '').strip().lower()
        role = request.data.get('role', 'viewer')
        if role not in ROLE_RANK:
            return Response({'error': f'Invalid role: {role}'}, status=status.HTTP_400_BAD_REQUEST)
        if role == 'owner':
            return Response({'error': 'Cannot assign owner role'}, status=status.HTTP_400_BAD_REQUEST)
        # Cannot grant a role equal/higher than your own (unless you're owner)
        if caller_role != 'owner' and ROLE_RANK.get(role, 0) >= ROLE_RANK.get(caller_role, 0):
            return Response({'error': 'Cannot grant a role equal or above your own'}, status=status.HTTP_403_FORBIDDEN)
        from apps.core.models import User as UserModel
        try:
            target_user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            return Response({'error': f'No user found with email: {email}'}, status=status.HTTP_404_NOT_FOUND)
        if target_user == qr.created_by:
            return Response({'error': 'Cannot modify the owner'}, status=status.HTTP_400_BAD_REQUEST)
        access, created = QRCodeAccess.objects.update_or_create(
            qr_code=qr, user=target_user,
            defaults={'role': role, 'granted_by': request.user},
        )
        return Response(QRCodeAccessSerializer(access).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def patch(self, request, id):
        """Update role: body = { access_id, role }"""
        qr, caller_role, err = self._require(request, id, 'admin')
        if err:
            return err
        access_id = request.data.get('access_id')
        new_role = request.data.get('role', '')
        if new_role not in ROLE_RANK or new_role == 'owner':
            return Response({'error': f'Invalid role: {new_role}'}, status=status.HTTP_400_BAD_REQUEST)
        access = get_object_or_404(QRCodeAccess, id=access_id, qr_code=qr)
        if caller_role != 'owner' and ROLE_RANK.get(new_role, 0) >= ROLE_RANK.get(caller_role, 0):
            return Response({'error': 'Cannot grant a role equal or above your own'}, status=status.HTTP_403_FORBIDDEN)
        if caller_role != 'owner' and ROLE_RANK.get(access.role, 0) >= ROLE_RANK.get(caller_role, 0):
            return Response({'error': 'Cannot modify a user with equal or higher role'}, status=status.HTTP_403_FORBIDDEN)
        access.role = new_role
        access.save(update_fields=['role', 'updated_at'])
        return Response(QRCodeAccessSerializer(access).data)

    def delete(self, request, id):
        """Revoke: query param access_id"""
        qr, caller_role, err = self._require(request, id, 'admin')
        if err:
            return err
        access_id = request.query_params.get('access_id')
        if not access_id:
            return Response({'error': 'access_id required'}, status=status.HTTP_400_BAD_REQUEST)
        access = get_object_or_404(QRCodeAccess, id=access_id, qr_code=qr)
        if caller_role != 'owner' and ROLE_RANK.get(access.role, 0) >= ROLE_RANK.get(caller_role, 0):
            return Response({'error': 'Cannot revoke a user with equal or higher role'}, status=status.HTTP_403_FORBIDDEN)
        access.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class QRMyAccessView(APIView):
    """GET the caller's role for a given QR code."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        qr, role = _get_qr_for_role(request, id, 'viewer')
        if not qr:
            return Response({'role': None, 'has_access': False})
        return Response({'role': role, 'has_access': True})


# ════════════════════════════════════════════════════════
# POSTER GENERATOR (Feature 45)
# ════════════════════════════════════════════════════════

class PosterPresetsView(APIView):
    """GET available poster template presets and their dimensions."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        presets = [
            {'key': k, 'width': w, 'height': h}
            for k, (w, h) in POSTER_PRESETS.items()
        ]
        return Response(presets)


class PosterGenerateView(APIView):
    """POST — generate a poster/creative with embedded QR.  Returns PNG bytes."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        template = data.get('template', 'flyer')
        if template not in POSTER_PRESETS:
            return Response({'detail': f'Invalid template. Choose from: {", ".join(POSTER_PRESETS.keys())}'},
                            status=status.HTTP_400_BAD_REQUEST)

        title = (data.get('title') or '')[:120]
        subtitle = (data.get('subtitle') or '')[:200]
        bg_color = (data.get('bg_color') or '#1E293B')[:9]
        accent_color = (data.get('accent_color') or '#22D3EE')[:9]
        text_color = (data.get('text_color') or '#FFFFFF')[:9]
        qr_size = int(data.get('qr_size') or 0)

        try:
            png_bytes = generate_poster(
                qr, template=template, title=title, subtitle=subtitle,
                bg_color=bg_color, accent_color=accent_color,
                text_color=text_color, qr_size=qr_size,
            )
        except Exception as exc:
            logger.exception('Poster generation failed for QR %s: %s', id, exc)
            return Response({'detail': 'Poster generation failed.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = HttpResponse(png_bytes, content_type='image/png')
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title or 'poster')[:40]
        response['Content-Disposition'] = f'inline; filename="{qr.slug}_{template}_{safe_title}.png"'
        return response


# ════════════════════════════════════════════════════════
# FEATURE CONFLICT DETECTION (Feature Priority System)
# ════════════════════════════════════════════════════════

class FeatureStatusView(APIView):
    """
    GET /api/v1/qr/<id>/feature-status/

    Returns status of all features for a QR code with conflict warnings.
    Helps users understand which features are active and which are blocked
    by higher-priority features.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        features = get_all_feature_status(qr)
        conflicts = detect_feature_conflicts(features)

        # Find highest priority active feature
        highest_active = None
        for feat in features:
            if feat['is_active']:
                if highest_active is None or feat['priority'] < highest_active['priority']:
                    highest_active = feat

        return Response({
            'features': features,
            'conflicts': conflicts,
            'highest_priority_active': highest_active,
            'total_active': sum(1 for f in features if f['is_active']),
        })


class SimulateRedirectView(APIView):
    """
    POST /api/v1/qr/<id>/simulate/

    Dry-run the redirect engine without recording analytics.
    Returns which feature would handle the scan and the destination.

    Request body (all optional):
    {
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)...",
        "country": "US",
        "region": "CA",
        "city": "San Francisco",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "accept_language": "en-US,en;q=0.9"
    }
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        qr = _get_qr_with_access(request, id)
        if not qr:
            return Response({'detail': 'QR code not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Extract simulation parameters with defaults
        params = {
            'user_agent': request.data.get('user_agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'),
            'country': request.data.get('country', ''),
            'region': request.data.get('region', ''),
            'city': request.data.get('city', ''),
            'latitude': request.data.get('latitude'),
            'longitude': request.data.get('longitude'),
            'accept_language': request.data.get('accept_language', 'en-US'),
        }

        result = simulate_redirect(qr, params)
        return Response(result)
