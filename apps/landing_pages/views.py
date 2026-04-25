"""
Landing Pages — Views
=======================
Admin CRUD + Public page serving
"""
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.db.models import F
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.permissions import IsOrgMember
from .models import LandingPage, LandingPageTemplate, Popup, PopupSubmission
from .serializers import (
    LandingPageListSerializer,
    LandingPageDetailSerializer,
    LandingPageCreateSerializer,
    LandingPageTemplateSerializer,
    PopupListSerializer,
    PopupDetailSerializer,
    PopupCreateSerializer,
    PopupSubmissionSerializer,
)


# ─── Admin/API Views ──────────────────────────────────────────────────────────


class LandingPageListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/landing-pages/
    POST /api/v1/landing-pages/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return LandingPageCreateSerializer
        return LandingPageListSerializer

    def get_queryset(self):
        return LandingPage.objects.filter(organization=self.request.user.organization)


class LandingPageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/v1/landing-pages/<id>/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return LandingPageCreateSerializer
        return LandingPageDetailSerializer

    def get_queryset(self):
        return LandingPage.objects.filter(organization=self.request.user.organization)


class LandingPagePublishToggleView(APIView):
    """POST /api/v1/landing-pages/<id>/publish/ — Toggle publish status."""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            page = LandingPage.objects.get(id=id, organization=request.user.organization)
        except LandingPage.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        page.is_published = not page.is_published
        page.save(update_fields=['is_published', 'updated_at'])
        return Response({'id': str(page.id), 'is_published': page.is_published})


class LandingPageDuplicateView(APIView):
    """POST /api/v1/landing-pages/<id>/duplicate/ — Clone a page."""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            page = LandingPage.objects.get(id=id, organization=request.user.organization)
        except LandingPage.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        import uuid
        new_page = LandingPage.objects.create(
            organization=page.organization,
            created_by=request.user,
            qr_code=None,
            template=page.template,
            title=f"{page.title} (Copy)",
            slug=f"{page.slug}-{uuid.uuid4().hex[:6]}",
            meta_description=page.meta_description,
            html_content=page.html_content,
            custom_css=page.custom_css,
            custom_js=page.custom_js,
            page_config=page.page_config,
            show_qrgenie_badge=page.show_qrgenie_badge,
            is_ai_generated=page.is_ai_generated,
            is_published=False,
        )
        return Response(LandingPageDetailSerializer(new_page).data, status=status.HTTP_201_CREATED)


class TemplateListView(generics.ListAPIView):
    """GET /api/v1/landing-pages/templates/ — List available templates."""
    serializer_class = LandingPageTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = LandingPageTemplate.objects.filter(is_active=True)


# ─── Public Page Serving ──────────────────────────────────────────────────────


class LandingPagePublicView(APIView):
    """
    GET /p/<slug>/
    Serve the landing page HTML publicly. No auth required.
    Injects __PAGE_SLUG__ → actual slug so JS features (password verify,
    download tracking, event tracking) know their own slug at runtime.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        page = get_object_or_404(LandingPage, slug=slug, is_published=True)

        # Increment view counter
        LandingPage.objects.filter(id=page.id).update(view_count=F('view_count') + 1)

        html = page.html_content

        # ── Replace the slug placeholder so embedded JS knows its own slug ──
        html = html.replace('__PAGE_SLUG__', page.slug)

        # Inject custom CSS if present
        if page.custom_css:
            css_tag = f"<style>{page.custom_css}</style>"
            html = html.replace('</head>', f'{css_tag}</head>')

        # Inject QRGenie badge if enabled
        if page.show_qrgenie_badge:
            badge = (
                '<div style="position:fixed;bottom:12px;right:12px;background:#6366f1;'
                'color:#fff;padding:6px 14px;border-radius:20px;font-size:12px;'
                'font-family:sans-serif;z-index:9999;opacity:0.85;">'
                '<a href="https://qrgenie.io" style="color:#fff;text-decoration:none;" '
                'target="_blank">Powered by QRGenie</a></div>'
            )
            html = html.replace('</body>', f'{badge}</body>')

        # ── Inject link-click tracking script (Feature 23) ──
        qr_id = str(page.qr_code_id) if page.qr_code_id else ''
        if qr_id:
            tracking_script = (
                '<script>'
                '(function(){'
                'var qid="' + qr_id + '";'
                'document.addEventListener("click",function(e){'
                'var a=e.target.closest("a[href]");'
                'if(!a)return;'
                'var h=a.href;'
                'if(!h||h.startsWith("javascript:")||h==="#")return;'
                'var lb=a.textContent.trim().substring(0,200);'
                'try{navigator.sendBeacon("/api/v1/analytics/click/",'
                'new Blob([JSON.stringify({qr_id:qid,link_url:h,link_label:lb})],'
                '{type:"application/json"}));'
                '}catch(x){}'
                '});'
                '})();'
                '</script>'
            )
            html = html.replace('</body>', f'{tracking_script}</body>')

        response = HttpResponse(html, content_type='text/html')
        # Defense-in-depth: prevent data exfiltration from user/AI-generated scripts.
        # connect-src 'self' means fetch()/XHR cannot send data to external origins.
        # frame-ancestors 'none' prevents clickjacking of the landing page.
        response['Content-Security-Policy'] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


# ─── Per-page-type public endpoints ──────────────────────────────────────────


class PasswordVerifyView(APIView):
    """
    POST /p/<slug>/verify/
    Verify the password for a password-protected landing page.
    Returns the unlocked HTML content on success.
    No auth required (public endpoint).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, slug):
        from django.contrib.auth.hashers import check_password as django_check_pw

        page = get_object_or_404(LandingPage, slug=slug, is_published=True)

        if page.page_config.get('page_type') != 'password':
            return Response(
                {'detail': 'Not a password-protected page.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        submitted = (request.data.get('password') or '').strip()
        stored_hash = page.page_config.get('password_hash', '')

        if not submitted or not stored_hash:
            return Response({'detail': 'Incorrect password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not django_check_pw(submitted, stored_hash):
            return Response({'detail': 'Incorrect password.'}, status=status.HTTP_401_UNAUTHORIZED)

        # ── Build unlocked content HTML ───────────────────────────────────
        fd = page.page_config.get('form_data', {})
        content_title = fd.get('content_title') or 'Welcome!'
        content_body  = fd.get('content_body')  or ''
        page_title    = fd.get('title') or page.title

        badge = (
            '<div style="position:fixed;bottom:12px;right:12px;background:#6366f1;'
            'color:#fff;padding:6px 14px;border-radius:20px;font-size:12px;'
            'font-family:sans-serif;z-index:9999;opacity:0.85;">'
            '<a href="https://qrgenie.io" style="color:#fff;text-decoration:none;" '
            'target="_blank">Powered by QRGenie</a></div>'
        ) if page.show_qrgenie_badge else ''

        content_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <link rel="stylesheet"
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <style>
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #f0fdf4, #dcfce7);
      font-family: system-ui, sans-serif;
      padding: 24px;
    }}
    .unlock-card {{
      background: #fff;
      border-radius: 20px;
      padding: 40px 32px;
      box-shadow: 0 12px 40px rgba(0,0,0,.08);
      max-width: 520px;
      width: 100%;
      text-align: center;
    }}
    .unlock-icon {{ font-size: 52px; margin-bottom: 18px; }}
    .unlock-title {{ font-size: 26px; font-weight: 800; color: #111; margin-bottom: 14px; }}
    .unlock-body  {{ font-size: 14px; color: #555; line-height: 1.75;
                    white-space: pre-wrap; text-align: left; }}
  </style>
</head>
<body>
  <div class="unlock-card">
    <div class="unlock-icon">🔓</div>
    <h1 class="unlock-title">{content_title}</h1>
    <div class="unlock-body">{content_body}</div>
  </div>
  {badge}
</body>
</html>"""

        return Response({'unlocked': True, 'content_html': content_html})


class FileDownloadView(APIView):
    """
    GET /p/<slug>/download/
    Serve the file as a forced download attachment.
    For locally uploaded media files the file is streamed directly.
    For external URLs we fall back to a redirect (browser will handle it).
    No auth required (public endpoint).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        import os
        from django.conf import settings
        from django.http import FileResponse

        page = get_object_or_404(LandingPage, slug=slug, is_published=True)

        if page.page_config.get('page_type') != 'file_delivery':
            return Response(
                {'detail': 'Not a file delivery page.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form_data = page.page_config.get('form_data') or {}
        file_url = form_data.get('file_url', '')
        if not file_url:
            return Response(
                {'detail': 'No file configured for this page.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Track download count in page_config events
        try:
            cfg = dict(page.page_config)
            events = dict(cfg.get('events', {}))
            events['download'] = events.get('download', 0) + 1
            cfg['events'] = events
            LandingPage.objects.filter(id=page.id).update(page_config=cfg)
        except Exception:
            pass

        # --- Serve local media files as a forced attachment download ---
        # Accept  /media/...  or  http(s)://host/media/...
        media_marker = '/media/'
        if media_marker in file_url:
            # Isolate the path after /media/
            relative_path = file_url[file_url.index(media_marker) + len(media_marker):]
            file_path = os.path.join(settings.MEDIA_ROOT, relative_path)
            if os.path.isfile(file_path):
                download_name = form_data.get('filename') or os.path.basename(file_path)
                response = FileResponse(
                    open(file_path, 'rb'),
                    as_attachment=True,
                    filename=download_name,
                )
                return response

        # --- Fallback: redirect (handles external URLs) ---
        return HttpResponseRedirect(file_url)


class PageEventView(APIView):
    """
    POST /p/<slug>/event/
    Lightweight event tracker for any page interaction (view, click, conversion).
    Body: { "event": "string label", "meta": {} }
    No auth required (public endpoint).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, slug):
        page = get_object_or_404(LandingPage, slug=slug)
        event_label = (request.data.get('event') or 'click')[:80]

        try:
            cfg = dict(page.page_config)
            events = dict(cfg.get('events', {}))
            events[event_label] = events.get(event_label, 0) + 1
            cfg['events'] = events
            LandingPage.objects.filter(id=page.id).update(page_config=cfg)
        except Exception:
            pass

        return Response({'ok': True})


class NewsletterSubscribeView(APIView):
    """
    POST /p/<slug>/subscribe/
    Store an email subscriber for a newsletter landing page.
    Body: { "email": "...", "name": "..." }
    No auth required (public endpoint).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, slug):
        import re
        page = get_object_or_404(LandingPage, slug=slug, is_published=True)

        email = (request.data.get('email') or '').strip().lower()
        name  = (request.data.get('name')  or '').strip()[:120]

        if not email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return Response(
                {'detail': 'Please provide a valid email address.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Store subscribers list inside page_config['subscribers']
        try:
            cfg = dict(page.page_config)
            subscribers = list(cfg.get('subscribers', []))

            # Check for duplicate
            if any(s.get('email') == email for s in subscribers):
                return Response({'detail': 'You are already subscribed!'}, status=status.HTTP_200_OK)

            from django.utils import timezone
            subscribers.append({
                'email': email,
                'name': name,
                'subscribed_at': timezone.now().isoformat(),
            })
            cfg['subscribers'] = subscribers
            LandingPage.objects.filter(id=page.id).update(page_config=cfg)
        except Exception:
            return Response({'detail': 'Could not save subscription.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'ok': True, 'detail': 'Subscribed successfully!'})


class SurveySubmitView(APIView):
    """
    POST /p/<slug>/submit/
    Store survey/form responses for a survey landing page.
    Body: { "ratings": {}, "answers": {} }
    No auth required (public endpoint).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, slug):
        page = get_object_or_404(LandingPage, slug=slug, is_published=True)

        ratings = request.data.get('ratings', {})
        answers = request.data.get('answers', {})

        if not ratings and not answers:
            return Response(
                {'detail': 'No response data provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cfg = dict(page.page_config)
            responses = list(cfg.get('survey_responses', []))

            from django.utils import timezone
            # Collect safely — strip any extremely long values
            safe_answers = {k: str(v)[:500] for k, v in (answers or {}).items()}
            safe_ratings = {k: int(v) for k, v in (ratings or {}).items() if str(v).isdigit()}

            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))[:45]
            responses.append({
                'ratings': safe_ratings,
                'answers': safe_answers,
                'ip': ip,
                'submitted_at': timezone.now().isoformat(),
            })
            cfg['survey_responses'] = responses
            LandingPage.objects.filter(id=page.id).update(page_config=cfg)
        except Exception:
            return Response({'detail': 'Could not save response.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'ok': True, 'detail': 'Response submitted. Thank you!'})


# ════════════════════════════════════════════════════════
# MEDIA / FILE UPLOAD  (for landing page builder)
# ════════════════════════════════════════════════════════

class MediaUploadView(APIView):
    """
    POST /api/v1/landing-pages/media/upload/
    Upload any media file (image, video, audio, PDF, doc, zip …) from the
    user's device for use in landing page content.

    Request: multipart/form-data  { file: <binary> }
    Response: { url, name, size, mime_type }

    Files are stored at  MEDIA_ROOT/page_uploads/<uuid>/<safe_filename>
    and served by Django's MEDIA_URL in development.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    MAX_SIZE_BYTES = 50 * 1024 * 1024   # 50 MB hard limit

    ALLOWED_MIME_PREFIXES = (
        'image/',
        'video/',
        'audio/',
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument',
        'application/vnd.ms-',          # old Office formats
        'application/zip',
        'application/x-zip',
        'application/x-zip-compressed',
        'application/octet-stream',     # generic binary (APKs etc.)
        'text/plain',
        'text/csv',
    )

    @staticmethod
    def _safe_filename(name: str) -> str:
        import unicodedata, re
        # ASCII-ify
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
        # Keep only word chars, dots, hyphens
        name = re.sub(r'[^\w.\-]', '_', name)
        return (name.strip('._') or 'file')[:200]

    def post(self, request):
        import uuid, os
        from django.conf import settings

        file = request.FILES.get('file')
        if not file:
            return Response(
                {'detail': 'No file provided. Send multipart/form-data with key "file".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Size check ───────────────────────────────────────────────────────
        if file.size > self.MAX_SIZE_BYTES:
            mb = self.MAX_SIZE_BYTES // (1024 * 1024)
            return Response(
                {'detail': f'File is too large. Maximum allowed size is {mb} MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── MIME type check ──────────────────────────────────────────────────
        mime = (file.content_type or 'application/octet-stream').split(';')[0].strip().lower()
        if not any(mime.startswith(p) for p in self.ALLOWED_MIME_PREFIXES):
            return Response(
                {'detail': f'File type "{mime}" is not permitted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Save file ────────────────────────────────────────────────────────
        safe_name = self._safe_filename(file.name)
        folder_id = str(uuid.uuid4())
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'page_uploads', folder_id)
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, safe_name)

        with open(file_path, 'wb+') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # ── Build URL ────────────────────────────────────────────────────────
        relative_url = f"{settings.MEDIA_URL}page_uploads/{folder_id}/{safe_name}"
        absolute_url = request.build_absolute_uri(relative_url)

        return Response({
            'url': absolute_url,
            'relative_url': relative_url,
            'name': safe_name,
            'original_name': file.name,
            'size': file.size,
            'mime_type': mime,
        }, status=status.HTTP_201_CREATED)


# ════════════════════════════════════════════════════════
# POPUP BUILDER — Feature 14
# ════════════════════════════════════════════════════════


class PopupListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/popups/      — list popups
    POST /api/v1/popups/      — create popup
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PopupCreateSerializer
        return PopupListSerializer

    def get_queryset(self):
        return Popup.objects.filter(organization=self.request.user.organization)


class PopupDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/PATCH/DELETE /api/v1/popups/<id>/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return PopupCreateSerializer
        return PopupDetailSerializer

    def get_queryset(self):
        return Popup.objects.filter(organization=self.request.user.organization)


class PopupPublishToggleView(APIView):
    """POST /api/v1/popups/<id>/publish/ — Toggle publish status."""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            popup = Popup.objects.get(id=id, organization=request.user.organization)
        except Popup.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        popup.is_published = not popup.is_published
        popup.save(update_fields=['is_published', 'updated_at'])
        return Response({'id': str(popup.id), 'is_published': popup.is_published})


class PopupDuplicateView(APIView):
    """POST /api/v1/popups/<id>/duplicate/ — Clone popup."""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            popup = Popup.objects.get(id=id, organization=request.user.organization)
        except Popup.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        import uuid as _uuid
        new = Popup.objects.create(
            organization=popup.organization,
            created_by=request.user,
            name=f"{popup.name} (Copy)",
            popup_type=popup.popup_type,
            trigger=popup.trigger,
            trigger_value=popup.trigger_value,
            position=popup.position,
            show_overlay=popup.show_overlay,
            allow_close=popup.allow_close,
            show_once=popup.show_once,
            frequency_hours=popup.frequency_hours,
            content=popup.content,
            style=popup.style,
            landing_page=popup.landing_page,
            is_active=popup.is_active,
            is_published=False,
        )
        return Response(PopupDetailSerializer(new).data, status=status.HTTP_201_CREATED)


class PopupSubmissionListView(generics.ListAPIView):
    """GET /api/v1/popups/<id>/submissions/ — List form submissions for a popup."""
    serializer_class = PopupSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return PopupSubmission.objects.filter(
            popup__id=self.kwargs['id'],
            popup__organization=self.request.user.organization,
        )


# ── Public Popup Endpoints (no auth) ─────────────────────────────────────────


class PopupEmbedView(APIView):
    """
    GET /popup/<token>/embed.js
    Returns a JavaScript snippet that renders the popup on the host page.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        popup = get_object_or_404(Popup, embed_token=token, is_published=True, is_active=True)

        # Increment view
        Popup.objects.filter(id=popup.id).update(view_count=F('view_count') + 1)

        import json
        config = {
            'id': str(popup.id),
            'type': popup.popup_type,
            'trigger': popup.trigger,
            'triggerValue': popup.trigger_value,
            'position': popup.position,
            'showOverlay': popup.show_overlay,
            'allowClose': popup.allow_close,
            'showOnce': popup.show_once,
            'frequencyHours': popup.frequency_hours,
            'content': popup.content,
            'style': popup.style,
        }
        config_json = json.dumps(config)

        js = self._build_embed_js(config_json, str(popup.embed_token))
        return HttpResponse(js, content_type='application/javascript')

    @staticmethod
    def _build_embed_js(config_json, token):
        return f"""(function(){{
  if(window.__qrgenie_popup_loaded)return;
  window.__qrgenie_popup_loaded=true;
  var C={config_json};
  var S=C.style||{{}};
  var bgC=S.bg_color||'#ffffff';
  var txC=S.text_color||'#111111';
  var acC=S.accent_color||'#2563EB';
  var bR=(S.border_radius||16)+'px';
  var wid=S.width||'480px';
  var overlay=null,popup=null;

  function build(){{
    // overlay
    if(C.showOverlay){{
      overlay=document.createElement('div');
      overlay.id='qrg-popup-overlay';
      overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:99998;opacity:0;transition:opacity .3s';
      document.body.appendChild(overlay);
      setTimeout(function(){{overlay.style.opacity='1'}},10);
      if(C.allowClose)overlay.addEventListener('click',close);
    }}
    // popup container
    popup=document.createElement('div');
    popup.id='qrg-popup';
    var pos=posStyle();
    popup.style.cssText='position:fixed;z-index:99999;'+pos+'background:'+bgC+';color:'+txC+';border-radius:'+bR+';box-shadow:0 20px 60px rgba(0,0,0,.2);max-width:'+wid+';width:92%;font-family:system-ui,sans-serif;transform:scale(.9);opacity:0;transition:all .3s ease';
    popup.innerHTML=contentHTML();
    document.body.appendChild(popup);
    setTimeout(function(){{popup.style.transform='scale(1)';popup.style.opacity='1'}},20);
    if(C.allowClose){{
      var cb=popup.querySelector('[data-close]');
      if(cb)cb.addEventListener('click',close);
    }}
    // CTA click tracking
    var cta=popup.querySelector('[data-cta]');
    if(cta)cta.addEventListener('click',function(){{
      fetch('/popup/'+'{token}'+'/click/',{{method:'POST',headers:{{'Content-Type':'application/json'}}}}).catch(function(){{}});
    }});
  }}

  function posStyle(){{
    switch(C.position){{
      case'bottom':return'bottom:0;left:0;right:0;border-radius:'+bR+' '+bR+' 0 0;';
      case'top':return'top:0;left:0;right:0;border-radius:0 0 '+bR+' '+bR+';';
      case'slide_left':return'top:50%;left:20px;transform:translateY(-50%) translateX(-120%);';
      case'slide_right':return'top:50%;right:20px;transform:translateY(-50%) translateX(120%);';
      case'fullscreen':return'inset:0;border-radius:0;max-width:100%;width:100%;';
      default:return'top:50%;left:50%;transform:translate(-50%,-50%) scale(.9);';
    }}
  }}

  function contentHTML(){{
    var cn=C.content||{{}};
    var cls=C.allowClose?'<button data-close style="position:absolute;top:12px;right:14px;background:none;border:none;font-size:22px;cursor:pointer;color:'+txC+'">&times;</button>':'';
    var h='<h2 style="margin:0 0 10px;font-size:22px;font-weight:700">'+(cn.headline||'')+'</h2>';
    var b=cn.body?'<p style="margin:0 0 16px;font-size:14px;line-height:1.6;opacity:.85">'+cn.body+'</p>':'';
    var cta=cn.cta_text?'<a data-cta href="'+(cn.cta_url||'#')+'" style="display:inline-block;padding:12px 28px;background:'+acC+';color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">'+cn.cta_text+'</a>':'';
    var extra='';
    if(C.type==='video'&&cn.video_url){{
      extra='<div style="margin:12px 0;position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px"><iframe src="'+cn.video_url+'" style="position:absolute;inset:0;width:100%;height:100%;border:none" allowfullscreen></iframe></div>';
    }}
    if(C.type==='timer'&&cn.target_date){{
      extra='<div id="qrg-timer" style="font-size:28px;font-weight:800;letter-spacing:2px;margin:16px 0;color:'+acC+'">...</div>';
      setTimeout(startTimer,50);
    }}
    if(C.type==='form'){{
      var fields=(cn.fields||[]).map(function(f){{
        return '<input name="'+f.name+'" placeholder="'+(f.label||f.name)+'" '+(f.required?'required ':'')+' style="display:block;width:100%;padding:10px 14px;margin:0 0 10px;border:1px solid #ddd;border-radius:8px;font-size:14px;box-sizing:border-box">';
      }}).join('');
      extra='<form id="qrg-form" style="margin:12px 0">'+fields+'<button type="submit" style="padding:12px 28px;background:'+acC+';color:#fff;border:none;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer">'+(cn.submit_text||'Submit')+'</button></form>';
      setTimeout(function(){{
        var fm=document.getElementById('qrg-form');
        if(fm)fm.addEventListener('submit',function(e){{
          e.preventDefault();
          var d={{}};
          new FormData(fm).forEach(function(v,k){{d[k]=v}});
          fetch('/popup/'+'{token}'+'/submit/',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}}).then(function(){{
            fm.innerHTML='<p style="color:'+acC+';font-weight:600">'+(cn.success_message||'Thank you!')+'</p>';
          }}).catch(function(){{}});
        }});
      }},50);
    }}
    var img=cn.image_url?'<img src="'+cn.image_url+'" style="width:100%;border-radius:8px;margin:0 0 16px" />':'';
    return '<div style="position:relative;padding:32px">'+cls+img+h+extra+b+cta+'</div>';
  }}

  function startTimer(){{
    var el=document.getElementById('qrg-timer');
    if(!el)return;
    var td=new Date(C.content.target_date).getTime();
    var iv=setInterval(function(){{
      var n=td-Date.now();
      if(n<=0){{clearInterval(iv);el.textContent=(C.content.expired_text||'Expired!');return;}}
      var d=Math.floor(n/86400000),h=Math.floor(n%86400000/3600000),m=Math.floor(n%3600000/60000),s=Math.floor(n%60000/1000);
      el.textContent=d+'d '+h+'h '+m+'m '+s+'s';
    }},1000);
  }}

  function close(){{
    if(popup){{popup.style.transform='scale(.9)';popup.style.opacity='0';}}
    if(overlay)overlay.style.opacity='0';
    setTimeout(function(){{if(popup)popup.remove();if(overlay)overlay.remove();}},300);
    if(C.showOnce){{
      try{{document.cookie='qrg_popup_{token}=1;max-age='+(C.frequencyHours*3600)+';path=/'}}catch(e){{}}
    }}
  }}

  function shouldShow(){{
    if(C.showOnce){{
      if(document.cookie.indexOf('qrg_popup_{token}')!==-1)return false;
    }}
    return true;
  }}

  function trigger(){{
    if(!shouldShow())return;
    switch(C.trigger){{
      case'on_load':build();break;
      case'delay':setTimeout(build,(C.triggerValue||3)*1000);break;
      case'scroll':
        var fired=false;
        window.addEventListener('scroll',function(){{
          if(fired)return;
          var pct=window.scrollY/(document.body.scrollHeight-window.innerHeight)*100;
          if(pct>=(C.triggerValue||50)){{fired=true;build();}}
        }});
        break;
      case'exit':
        document.addEventListener('mouseout',function(e){{
          if(!e.relatedTarget&&e.clientY<5)build();
        }},{{once:true}});
        break;
      case'click':
        document.querySelectorAll('[data-qrg-popup]').forEach(function(el){{
          el.addEventListener('click',function(e){{e.preventDefault();build();}});
        }});
        break;
    }}
  }}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',trigger);
  else trigger();
}})();"""


class PopupClickTrackView(APIView):
    """POST /popup/<token>/click/ — Track CTA click."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        Popup.objects.filter(embed_token=token, is_published=True).update(
            click_count=F('click_count') + 1,
        )
        return Response({'ok': True})


class PopupSubmitView(APIView):
    """POST /popup/<token>/submit/ — Handle form submission from embed."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        popup = get_object_or_404(Popup, embed_token=token, is_published=True)
        Popup.objects.filter(id=popup.id).update(submit_count=F('submit_count') + 1)

        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))[:45]
        PopupSubmission.objects.create(
            popup=popup,
            data=request.data or {},
            ip_address=ip if ip else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            page_url=request.META.get('HTTP_REFERER', '')[:500],
        )
        return Response({'ok': True})
