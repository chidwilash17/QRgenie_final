"""
PDF Viewer — Public Views (Feature 11)
========================================
Serves the inline PDF viewer (PDF.js) and raw PDF file,
both secured by per-document access tokens.

Routes (registered in root urls.py):
  GET /pdf/<token>/       → HTML viewer with embedded PDF.js
  GET /pdf/<token>/raw/   → Raw PDF bytes (streamed to PDF.js worker)
"""
import os
import logging
from django.conf import settings
from django.http import (
    HttpResponse, FileResponse, Http404, JsonResponse,
)
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F

logger = logging.getLogger('apps.qrcodes')


def _get_pdf_by_token(token: str):
    """Look up active PDFDocument by access_token UUID."""
    from .models import PDFDocument
    try:
        return PDFDocument.objects.select_related('qr_code').get(
            access_token=token, is_active=True,
        )
    except PDFDocument.DoesNotExist:
        return None


class PDFViewerPageView(View):
    """
    GET /pdf/<token>/
    Serves the inline PDF.js viewer HTML page.
    No authentication required — secured by token.
    """
    def get(self, request, token):
        pdf_doc = _get_pdf_by_token(token)
        if not pdf_doc:
            raise Http404("PDF not found or access link has expired.")

        # Increment view count in background (non-blocking)
        try:
            from .models import PDFDocument
            PDFDocument.objects.filter(id=pdf_doc.id).update(view_count=F('view_count') + 1)
        except Exception:
            pass

        context = {
            'pdf_doc': pdf_doc,
            'pdf_url': request.build_absolute_uri(f'/pdf/{token}/raw/'),
            'title': pdf_doc.title or pdf_doc.original_filename,
            'allow_download': pdf_doc.allow_download,
            'page_count': pdf_doc.page_count,
            'file_size': pdf_doc.file_size,
        }
        return render(request, 'qrcodes/pdf_viewer.html', context)


class PDFRawFileView(View):
    """
    GET /pdf/<token>/raw/
    Streams the raw PDF bytes for PDF.js to render.
    Sets Content-Disposition: inline (not attachment) to prevent download prompt.
    """
    def get(self, request, token):
        pdf_doc = _get_pdf_by_token(token)
        if not pdf_doc:
            raise Http404("PDF not found.")

        file_path = os.path.join(settings.MEDIA_ROOT, pdf_doc.file_path)
        if not os.path.isfile(file_path):
            logger.error(f"[PDF] File missing on disk: {file_path}")
            raise Http404("PDF file not found on server.")

        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf',
        )
        # Inline disposition — do NOT trigger download
        safe_name = pdf_doc.original_filename.replace('"', '\\"')
        response['Content-Disposition'] = f'inline; filename="{safe_name}"'
        response['Content-Length'] = pdf_doc.file_size

        # Allow PDF.js CORS access — same origin only; wildcard would let any
        # website read private PDF bytes via JS fetch().
        response['Access-Control-Allow-Origin'] = settings.SITE_BASE_URL

        return response
