"""
Video Player — Public Views (Feature 13)
==========================================
Serves the inline Video.js player and raw video file,
both secured by per-document access tokens.

Routes (registered in root urls.py):
  GET /video/<token>/       → HTML player with Video.js
  GET /video/<token>/raw/   → Raw video bytes (streamed)
"""
import os
import re
import logging
from django.conf import settings
from django.http import (
    HttpResponse, FileResponse, Http404, StreamingHttpResponse,
)
from django.shortcuts import render
from django.views import View
from django.db.models import F

logger = logging.getLogger('apps.qrcodes')


def _get_video_by_token(token: str):
    """Look up active VideoDocument by access_token UUID."""
    from .models import VideoDocument
    try:
        return VideoDocument.objects.select_related('qr_code').get(
            access_token=token, is_active=True,
        )
    except VideoDocument.DoesNotExist:
        return None


class VideoPlayerPageView(View):
    """
    GET /video/<token>/
    Serves the Video.js HTML5 player page.
    No authentication required — secured by token.
    """
    def get(self, request, token):
        video_doc = _get_video_by_token(token)
        if not video_doc:
            raise Http404("Video not found or access link has expired.")

        # Increment view count
        try:
            from .models import VideoDocument
            VideoDocument.objects.filter(id=video_doc.id).update(view_count=F('view_count') + 1)
        except Exception:
            pass

        context = {
            'video_doc': video_doc,
            'video_url': request.build_absolute_uri(f'/video/{token}/raw/'),
            'title': video_doc.title or video_doc.original_filename,
            'allow_download': video_doc.allow_download,
            'autoplay': video_doc.autoplay,
            'loop': video_doc.loop,
            'mime_type': video_doc.mime_type,
            'duration': video_doc.duration_seconds,
            'file_size': video_doc.file_size,
        }
        return render(request, 'qrcodes/video_player.html', context)


class VideoRawFileView(View):
    """
    GET /video/<token>/raw/
    Streams the raw video bytes. Supports HTTP Range requests
    for seeking and progressive playback.
    """
    def get(self, request, token):
        video_doc = _get_video_by_token(token)
        if not video_doc:
            raise Http404("Video not found.")

        file_path = os.path.join(settings.MEDIA_ROOT, video_doc.file_path)
        if not os.path.isfile(file_path):
            logger.error(f"[Video] File missing on disk: {file_path}")
            raise Http404("Video file not found on server.")

        file_size = os.path.getsize(file_path)
        content_type = video_doc.mime_type or 'video/mp4'

        # Handle HTTP Range requests for seeking
        range_header = request.META.get('HTTP_RANGE', '')
        if range_header:
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                f = open(file_path, 'rb')
                f.seek(start)

                response = HttpResponse(
                    f.read(length),
                    status=206,
                    content_type=content_type,
                )
                response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                response['Content-Length'] = length
                response['Accept-Ranges'] = 'bytes'
                response['Access-Control-Allow-Origin'] = settings.SITE_BASE_URL
                f.close()
                return response

        # Full file response
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type,
        )
        safe_name = video_doc.original_filename.replace('"', '\\"')
        response['Content-Disposition'] = f'inline; filename="{safe_name}"'
        response['Content-Length'] = file_size
        response['Accept-Ranges'] = 'bytes'
        response['Access-Control-Allow-Origin'] = settings.SITE_BASE_URL

        return response
