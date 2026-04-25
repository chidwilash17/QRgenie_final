"""
AI Service â€” Views
====================
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.permissions import IsOrgMember
from apps.core.sanitize import strip_dangerous_html
from .models import AIGenerationLog
from .serializers import (
    AIGenerationLogSerializer,
    GenerateLandingPageRequestSerializer,
    AnalyticsSummaryRequestSerializer,
    SmartRouteRequestSerializer,
    ABOptimizeRequestSerializer,
)
from .client import (
    generate_landing_page_html,
    generate_analytics_summary,
    suggest_smart_routing,
    optimize_ab_test,
)


class AIGenerateLandingPageView(APIView):
    """
    POST /api/v1/ai/generate-landing-page/
    Generate an AI-powered landing page synchronously or async.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        serializer = GenerateLandingPageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org = request.user.organization
        # Check AI token budget
        from django.db.models import Sum
        used_tokens = AIGenerationLog.objects.filter(
            organization=org, status='completed'
        ).aggregate(total=Sum('total_tokens'))['total'] or 0

        if used_tokens >= org.max_ai_tokens_per_month:
            return Response(
                {'detail': f'AI token limit reached ({org.max_ai_tokens_per_month}). Upgrade plan.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        async_mode = request.query_params.get('async', 'false').lower() == 'true'

        if async_mode:
            from .tasks import generate_landing_page
            task = generate_landing_page.delay(
                qr_id=str(data.get('qr_id', '')),
                prompt=data['description'],
                org_id=str(org.id),
                user_id=str(request.user.id),
            )
            return Response({'task_id': str(task.id), 'status': 'processing'}, status=status.HTTP_202_ACCEPTED)

        # Synchronous generation
        log = AIGenerationLog.objects.create(
            organization=org,
            user=request.user,
            generation_type='landing_page',
            status='processing',
            prompt=data['description'],
            qr_code_id=data.get('qr_id'),
        )

        try:
            result = generate_landing_page_html(
                business_name=data['business_name'],
                business_type=data['business_type'],
                description=data['description'],
                links=data.get('links', []),
                style=data.get('style', 'modern'),
                color_scheme=data.get('color_scheme', '#6366f1'),
            )

            from django.utils import timezone
            log.status = 'completed'
            log.result = result
            log.total_tokens = result.get('tokens_used', 0)
            log.completed_at = timezone.now()
            log.save()

            return Response(result)

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log.save()
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIAnalyticsSummaryView(APIView):
    """
    POST /api/v1/ai/analytics-summary/
    Generate AI analytics summary for a QR code.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        serializer = AnalyticsSummaryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qr_id = str(serializer.validated_data['qr_id'])

        from apps.analytics.models import ScanEvent
        from django.db.models import Count

        scans = ScanEvent.objects.filter(
            qr_code_id=qr_id,
            qr_code__organization=request.user.organization,
        )
        if not scans.exists():
            return Response({'detail': 'No scan data found.'}, status=status.HTTP_404_NOT_FOUND)

        analytics_data = {
            'total_scans': scans.count(),
            'unique_scans': scans.filter(is_unique=True).count(),
            'top_countries': list(scans.values('country').annotate(c=Count('id')).order_by('-c')[:10]),
            'top_devices': list(scans.values('device_type').annotate(c=Count('id')).order_by('-c')),
            'top_browsers': list(scans.values('browser').annotate(c=Count('id')).order_by('-c')[:5]),
        }

        result = generate_analytics_summary(analytics_data)
        return Response(result)


class AISmartRouteView(APIView):
    """
    POST /api/v1/ai/smart-route/
    Get AI routing rule suggestions.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        serializer = SmartRouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qr_id = str(serializer.validated_data['qr_id'])

        from apps.qrcodes.models import QRCode
        from apps.analytics.models import ScanEvent

        try:
            qr = QRCode.objects.get(id=qr_id, organization=request.user.organization)
        except QRCode.DoesNotExist:
            return Response({'detail': 'QR not found.'}, status=status.HTTP_404_NOT_FOUND)

        scans = ScanEvent.objects.filter(qr_code=qr).order_by('-scanned_at')[:100]
        scan_data = [
            {'country': s.country, 'device': s.device_type, 'os': s.os,
             'browser': s.browser, 'time': str(s.scanned_at)}
            for s in scans
        ]
        qr_data = {
            'title': qr.title, 'type': qr.qr_type,
            'destination': qr.destination_url, 'total_scans': qr.total_scans,
        }

        result = suggest_smart_routing(qr_data, scan_data)
        return Response(result)


class AIABOptimizeView(APIView):
    """
    POST /api/v1/ai/ab-optimize/
    Analyze A/B test results and recommend a winner.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        serializer = ABOptimizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = optimize_ab_test(serializer.validated_data['variants'])
        return Response(result)


class AIGenerationLogListView(generics.ListAPIView):
    """
    GET /api/v1/ai/logs/
    List AI generation logs for the org.
    """
    serializer_class = AIGenerationLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = AIGenerationLog.objects.filter(organization=self.request.user.organization)
        gen_type = self.request.query_params.get('type')
        if gen_type:
            qs = qs.filter(generation_type=gen_type)
        return qs


class AITokenUsageView(APIView):
    """
    GET /api/v1/ai/usage/
    Token usage summary for the organization.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get(self, request):
        from django.db.models import Sum
        org = request.user.organization
        logs = AIGenerationLog.objects.filter(organization=org, status='completed')
        totals = logs.aggregate(
            total_tokens=Sum('total_tokens'),
            prompt_tokens=Sum('prompt_tokens'),
            completion_tokens=Sum('completion_tokens'),
        )
        return Response({
            'total_tokens_used': totals['total_tokens'] or 0,
            'prompt_tokens': totals['prompt_tokens'] or 0,
            'completion_tokens': totals['completion_tokens'] or 0,
            'token_limit': org.max_ai_tokens_per_month,
            'remaining': max(0, org.max_ai_tokens_per_month - (totals['total_tokens'] or 0)),
            'total_requests': logs.count(),
        })


class GeneratePageView(APIView):
    """
    POST /api/v1/ai/generate-page/
    â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    Generate a styled landing page from structured form data, then
    automatically create a QR code that points to it.

    Request body:
      page_type   : "multi_link" | "payment" | "file_delivery" |
                    "password" | "product" | "chat"
      form_data   : dict â€” type-specific fields (see page_generator.py)
      theme       : "gradient" | "dark" | "minimal" | "vibrant"  (default: gradient)
      title       : display title for the landing page
      slug        : (optional) custom slug; auto-generated if not provided

    Response:
      { page: {...}, qr_code: {...}, public_url: "https://..." }
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    PAGE_TYPES = (
        # original 6
        "multi_link", "payment", "file_delivery", "password", "product", "chat",
        # new 19
        "menu", "booking", "store", "portfolio", "coupon", "event",
        "newsletter", "video", "music", "gallery", "vcard", "resume",
        "review", "announcement", "location", "survey", "age_verify",
        "countdown", "tracking",
    )

    def post(self, request):
        page_type = request.data.get("page_type", "")
        form_data = request.data.get("form_data", {})
        theme = request.data.get("theme", "gradient")
        title = request.data.get("title", "").strip() or "My Page"
        custom_slug = request.data.get("slug", "").strip()
        custom_html = request.data.get("custom_html", "").strip() if request.data.get("custom_html") else ""

        if page_type not in self.PAGE_TYPES:
            return Response(
                {"detail": f"Invalid page_type. Must be one of: {self.PAGE_TYPES}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(form_data, dict):
            return Response(
                {"detail": "form_data must be a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # â”€â”€ Generate HTML â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # If the frontend already rendered the chosen template, use it directly
        # so the saved page exactly matches what the user previewed.
        if custom_html:
            html_content = strip_dangerous_html(custom_html)
        else:
            try:
                from .page_generator import generate_page
                html_content = generate_page(page_type, form_data, theme)
            except Exception as e:
                return Response(
                    {"detail": f"Page generation failed: {e}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # â”€â”€ For password pages: hash the password before storing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        password_hash = None
        if page_type == 'password' and form_data.get('password'):
            from django.contrib.auth.hashers import make_password
            password_hash = make_password(form_data['password'])
            # Remove raw password from stored form_data for security
            form_data = {k: v for k, v in form_data.items() if k != 'password'}

        # â”€â”€ Build slug & public URL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        import uuid
        import re
        from django.conf import settings
        from apps.landing_pages.models import LandingPage
        from apps.qrcodes.models import QRCode

        # Slug: custom â†’ auto from title â†’ random
        if custom_slug:
            slug = re.sub(r'[^a-z0-9-]', '', custom_slug.lower().replace(' ', '-'))[:50]
        else:
            base_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:30]
            suffix = uuid.uuid4().hex[:6]
            slug = f"{base_slug}-{suffix}"

        # Ensure uniqueness
        if LandingPage.objects.filter(slug=slug).exists():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        # Resolve the base URL from SITE_BASE_URL
        base_url = getattr(settings, 'SITE_BASE_URL', 'http://localhost:8000').rstrip('/')
        public_url = f"{base_url}/p/{slug}/"

        # â”€â”€ Create LandingPage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        org = request.user.organization
        page_cfg = {"page_type": page_type, "form_data": form_data, "theme": theme}
        if password_hash:
            page_cfg["password_hash"] = password_hash
        lp = LandingPage.objects.create(
            organization=org,
            created_by=request.user,
            title=title,
            slug=slug,
            html_content=html_content,
            page_config=page_cfg,
            is_ai_generated=True,
            ai_prompt=f"{page_type} / {theme}",
            is_published=True,
            show_qrgenie_badge=True,
        )

        # â”€â”€ Create QR code pointing to the landing page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        qr_type_map = {
            "multi_link": "multi_link",
            "payment": "payment",
            "file_delivery": "file",
            "password": "landing_page",
            "product": "landing_page",
            "chat": "chat",
        }
        try:
            qr = QRCode.objects.create(
                organization=org,
                created_by=request.user,
                title=title,
                qr_type=qr_type_map.get(page_type, "landing_page"),
                destination_url=public_url,
                status="active",
            )
            # Generate the actual QR code image
            from apps.qrcodes.services import generate_qr_image
            img_url = generate_qr_image(qr)
            qr.qr_image_url = img_url
            qr.save(update_fields=["qr_image_url"])

            lp.qr_code = qr
            lp.save(update_fields=["qr_code", "updated_at"])
        except Exception as e:
            # QR creation failure is non-fatal; return the page anyway
            return Response({
                "page": {
                    "id": str(lp.id), "title": lp.title, "slug": lp.slug,
                    "public_url": public_url, "page_type": page_type, "theme": theme,
                },
                "qr_code": None,
                "public_url": public_url,
                "warning": f"QR creation failed: {e}",
            }, status=status.HTTP_201_CREATED)

        # â”€â”€ Build absolute QR image URL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        qr_image_url = None
        if qr.qr_image_url:
            try:
                if qr.qr_image_url.startswith('http'):
                    qr_image_url = qr.qr_image_url
                else:
                    qr_image_url = request.build_absolute_uri(qr.qr_image_url)
            except Exception:
                qr_image_url = qr.qr_image_url

        return Response({
            "page": {
                "id": str(lp.id),
                "title": lp.title,
                "slug": lp.slug,
                "public_url": public_url,
                "page_type": page_type,
                "theme": theme,
            },
            "qr_code": {
                "id": str(qr.id),
                "title": qr.title,
                "slug": qr.slug,
                "qr_image_url": qr_image_url,
                "destination_url": qr.destination_url,
                "qr_type": qr.qr_type,
            },
            "public_url": public_url,
        }, status=status.HTTP_201_CREATED)


class AIPlanPageView(APIView):
    """
    POST /api/v1/ai/plan-page/
    AI analyzes the user's prompt and returns a structured form schema
    with fields the user should fill in before generating the page.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        prompt = (request.data.get('prompt') or '').strip()
        if not prompt:
            return Response(
                {'detail': 'Please provide a prompt describing the page you want.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(prompt) > 5000:
            return Response(
                {'detail': 'Prompt too long (max 5000 characters).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = request.user.organization

        # Token budget check
        from django.db.models import Sum
        used_tokens = AIGenerationLog.objects.filter(
            organization=org, status='completed'
        ).aggregate(total=Sum('total_tokens'))['total'] or 0

        if used_tokens >= org.max_ai_tokens_per_month:
            return Response(
                {'detail': f'AI token limit reached ({org.max_ai_tokens_per_month}). Upgrade plan.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            from .client import ai_plan_page_fields
            result = ai_plan_page_fields(prompt=prompt)
        except Exception as e:
            return Response(
                {'detail': f'AI planning failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Log the planning tokens
        from django.utils import timezone as tz
        AIGenerationLog.objects.create(
            organization=org,
            user=request.user,
            generation_type='landing_page',
            status='completed',
            prompt=f'[PLAN] {prompt[:1900]}',
            total_tokens=result.get('tokens_used', 0),
            model_used=result.get('model', ''),
            completed_at=tz.now(),
        )

        return Response({
            'page_type': result.get('page_type', 'custom'),
            'description': result.get('description', ''),
            'suggested_tagline': result.get('suggested_tagline', ''),
            'suggested_sections': result.get('suggested_sections', []),
            'fields': result.get('fields', []),
            'tokens_used': result.get('tokens_used', 0),
        })


class AIPromptPageView(APIView):
    """
    POST /api/v1/ai/prompt-page/
    â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    Generate a complete landing page from a free-form AI prompt.
    The user describes what they want and the AI builds the entire page.

    Request body:
      prompt   : str â€” free-form description of the desired page
      style    : str â€” "modern" | "minimal" | "bold" | "elegant" | "playful" (default: modern)
      title    : str â€” (optional) page title override
      slug     : str â€” (optional) custom slug
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        prompt = (request.data.get('prompt') or '').strip()
        if not prompt:
            return Response(
                {'detail': 'Please provide a prompt describing the page you want.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(prompt) > 5000:
            return Response(
                {'detail': 'Prompt too long (max 5000 characters).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        style = request.data.get('style', 'modern').strip()
        title = (request.data.get('title') or '').strip()
        custom_slug = (request.data.get('slug') or '').strip()
        fields_data = request.data.get('fields_data') or {}
        linked_forms = request.data.get('linked_forms') or []
        page_type = (request.data.get('page_type') or '').strip()
        suggested_sections = request.data.get('suggested_sections') or []
        media_files = request.data.get('media_files') or []

        org = request.user.organization

        # Token budget check
        from django.db.models import Sum
        used_tokens = AIGenerationLog.objects.filter(
            organization=org, status='completed'
        ).aggregate(total=Sum('total_tokens'))['total'] or 0

        if used_tokens >= org.max_ai_tokens_per_month:
            return Response(
                {'detail': f'AI token limit reached ({org.max_ai_tokens_per_month}). Upgrade plan.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Create log entry
        log = AIGenerationLog.objects.create(
            organization=org,
            user=request.user,
            generation_type='landing_page',
            status='processing',
            prompt=prompt[:2000],
        )

        # Resolve linked forms into real URLs and generate smart button labels
        form_links = []
        if linked_forms:
            from apps.forms_builder.models import Form as UserForm
            from django.conf import settings as django_settings
            base_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:8000').rstrip('/')

            # Smart button label generator based on page type
            def generate_button_label(form_title, page_type_hint):
                """Generate contextual button label if user didn't provide one"""
                form_lower = form_title.lower()
                page_lower = (page_type_hint or '').lower()

                # Match button text to context
                if 'rsvp' in form_lower or 'rsvp' in page_lower:
                    return 'RSVP Now'
                elif 'register' in form_lower or 'registration' in form_lower or 'signup' in form_lower:
                    return 'Register Now'
                elif 'contact' in form_lower or 'inquiry' in form_lower:
                    return 'Contact Us'
                elif 'subscribe' in form_lower or 'newsletter' in form_lower:
                    return 'Subscribe'
                elif 'apply' in form_lower or 'application' in form_lower:
                    return 'Apply Now'
                elif 'book' in form_lower or 'booking' in form_lower or 'reservation' in form_lower:
                    return 'Book Now'
                elif 'join' in form_lower or 'waitlist' in form_lower:
                    return 'Join Waitlist'
                elif 'survey' in form_lower or 'feedback' in form_lower:
                    return 'Submit Feedback'
                elif 'order' in form_lower or 'purchase' in form_lower:
                    return 'Order Now'
                elif 'event' in page_lower or 'conference' in page_lower:
                    return 'Register for Event'
                elif 'wedding' in page_lower:
                    return 'RSVP to Wedding'
                elif 'product' in page_lower or 'launch' in page_lower:
                    return 'Get Early Access'
                else:
                    # Fallback: use form title
                    return f"Submit {form_title}"

            for lf in linked_forms:
                form_id = lf.get('form_id', '')
                btn_label = (lf.get('label', '') or '').strip()
                if form_id:
                    try:
                        uf = UserForm.objects.get(id=form_id, owner=request.user)
                        # Auto-generate label if empty
                        if not btn_label:
                            btn_label = generate_button_label(uf.title, page_type)
                        form_links.append({
                            'label': btn_label,
                            'url': f"{base_url}/f/{uf.slug}/",
                        })
                    except UserForm.DoesNotExist:
                        pass  # skip invalid form IDs silently

        try:
            from .client import ai_generate_page_from_prompt
            result = ai_generate_page_from_prompt(prompt=prompt, style_hint=style, fields_data=fields_data, form_links=form_links, page_type=page_type, suggested_sections=suggested_sections, media_files=media_files)
        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log.save()
            return Response(
                {'detail': f'AI generation failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Everything below is wrapped in try/except to catch silent 500s ──
        import logging as _logging
        _logger = _logging.getLogger('qrgenie')

        try:
            return self._build_page_response(request, result, log, org, prompt, title, style, custom_slug)
        except Exception as exc:
            _logger.exception(f'prompt-page post-AI error: {exc}')
            log.status = 'failed'
            log.error_message = f'Post-AI error: {exc}'
            try:
                log.save()
            except Exception:
                pass
            return Response(
                {'detail': f'Page creation failed after AI generation: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Extracted into a method so the try/except in post() catches everything
    def _build_page_response(self, request, result, log, org, prompt, title, style, custom_slug):
        html_content = strip_dangerous_html(result.get('html', ''))
        ai_title = result.get('title', 'AI Generated Page')
        meta_desc = result.get('meta_description', '')

        if not html_content:
            log.status = 'failed'
            log.error_message = 'AI returned empty HTML'
            log.save()
            return Response(
                {'detail': 'AI returned empty content. Try rewording your prompt.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        page_title = title or ai_title

        # Update log — store metadata only, not the huge HTML
        from django.utils import timezone as tz
        log.status = 'completed'
        log.result = {
            'title': result.get('title', ''),
            'meta_description': result.get('meta_description', ''),
            'tokens_used': result.get('tokens_used', 0),
            'model': result.get('model', ''),
            'html_length': len(html_content),
        }
        log.total_tokens = result.get('tokens_used', 0)
        log.model_used = (result.get('model', '') or '')[:100]
        log.completed_at = tz.now()
        log.save()

        # Build slug
        import uuid
        import re
        from django.conf import settings as django_settings
        from apps.landing_pages.models import LandingPage
        from apps.qrcodes.models import QRCode

        if custom_slug:
            slug = re.sub(r'[^a-z0-9-]', '', custom_slug.lower().replace(' ', '-'))[:50]
        else:
            base_slug = re.sub(r'[^a-z0-9]+', '-', page_title.lower()).strip('-')[:30]
            suffix = uuid.uuid4().hex[:6]
            slug = f"{base_slug}-{suffix}"

        if LandingPage.objects.filter(slug=slug).exists():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        base_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:8000').rstrip('/')
        public_url = f"{base_url}/p/{slug}/"

        # Create LandingPage
        lp = LandingPage.objects.create(
            organization=org,
            created_by=request.user,
            title=page_title,
            slug=slug,
            html_content=html_content,
            meta_description=meta_desc,
            page_config={
                'page_type': 'ai_prompt',
                'form_data': {},
                'ai_style': style,
            },
            is_ai_generated=True,
            ai_prompt=prompt[:2000],
            is_published=True,
            show_qrgenie_badge=True,
        )

        # Create QR code
        qr_image_url = None
        qr_data = None
        try:
            qr = QRCode.objects.create(
                organization=org,
                created_by=request.user,
                title=page_title,
                qr_type='landing_page',
                destination_url=public_url,
                status='active',
            )
            from apps.qrcodes.services import generate_qr_image
            img_url = generate_qr_image(qr)
            qr.qr_image_url = img_url
            qr.save(update_fields=['qr_image_url'])

            lp.qr_code = qr
            lp.save(update_fields=['qr_code', 'updated_at'])

            if qr.qr_image_url:
                qr_image_url = (
                    qr.qr_image_url
                    if qr.qr_image_url.startswith('http')
                    else request.build_absolute_uri(qr.qr_image_url)
                )

            qr_data = {
                'id': str(qr.id),
                'title': qr.title,
                'slug': qr.slug,
                'qr_image_url': qr_image_url,
                'destination_url': qr.destination_url,
                'qr_type': qr.qr_type,
            }
        except Exception as e:
            import logging
            logging.getLogger('qrgenie').error(f'QR creation for AI page failed: {e}')

        return Response({
            'page': {
                'id': str(lp.id),
                'title': lp.title,
                'slug': lp.slug,
                'public_url': public_url,
                'html_content': html_content,
                'meta_description': meta_desc,
                'is_ai_generated': True,
                'ai_prompt': prompt[:2000],
            },
            'qr_code': qr_data,
            'public_url': public_url,
            'tokens_used': result.get('tokens_used', 0),
        }, status=status.HTTP_201_CREATED)


class LinkFormToPageView(APIView):
    """
    POST /api/v1/ai/link-form-to-page/
    ─────────────────────────────────────
    Links a form to a landing page (metadata only).
    DOES NOT inject any HTML - form buttons should be created by AI during generation.

    Request body:
      page_id  : str — UUID of the landing page
      form_id  : str — UUID of the form to link
      button_label : str — CTA text (stored in metadata only)
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request):
        page_id = request.data.get('page_id', '').strip()
        form_id = request.data.get('form_id', '').strip()
        button_label = (request.data.get('button_label') or 'Register Now').strip()

        if not page_id or not form_id:
            return Response(
                {'detail': 'page_id and form_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.landing_pages.models import LandingPage
        from apps.forms_builder.models import Form as UserForm
        from django.conf import settings as django_settings

        try:
            lp = LandingPage.objects.get(id=page_id, organization=request.user.organization)
        except LandingPage.DoesNotExist:
            return Response({'detail': 'Landing page not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            form = UserForm.objects.get(id=form_id, owner=request.user)
        except UserForm.DoesNotExist:
            return Response({'detail': 'Form not found.'}, status=status.HTTP_404_NOT_FOUND)

        base_url = getattr(django_settings, 'SITE_BASE_URL', 'http://localhost:8000').rstrip('/')
        form_url = f"{base_url}/f/{form.slug}/"

        # REMOVED: HTML injection - form buttons should be created by AI during generation
        # Only store link metadata in page_config (no HTML modification)
        config = lp.page_config or {}
        config['linked_form_id'] = str(form.id)
        config['linked_form_url'] = form_url
        config['linked_form_label'] = button_label
        lp.page_config = config
        lp.save(update_fields=['page_config', 'updated_at'])

        return Response({
            'detail': 'Form linked to landing page successfully (metadata only - no HTML injection).',
            'page_id': str(lp.id),
            'form_id': str(form.id),
            'form_url': form_url,
            'page_url': f"{base_url}/p/{lp.slug}/",
        })


class AIChatAssistantView(APIView):
    """
    POST /api/v1/ai/chat/
    AI chat assistant that guides users about QRGenie features.
    Uses Groq API with Llama 3.3 70B.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    SYSTEM_PROMPT = """You are QRGenie AI Assistant — a helpful, friendly guide for the QRGenie platform. You MUST ONLY answer questions related to QRGenie features and usage. If a user asks anything unrelated to QRGenie, politely decline and redirect them to QRGenie topics.

When explaining features, provide clear step-by-step instructions and working examples. When a feature is relevant, include the navigation path so the user can go directly to it.

## QRGenie Platform Features & Navigation

### Dashboard
- **Dashboard** → `/dashboard` — Overview of all QR codes, scans, analytics at a glance.

### QR Code Management
- **QR Codes List** → `/qr` — View all your QR codes, search, filter, and manage them.
- **Create QR Code** → `/qr/create` — Create a new dynamic QR code. Choose a target URL, customize colors, add a logo, pick a style (dots, rounded, etc.), and download in PNG/SVG.
- **Bulk Upload** → `/qr/bulk-upload` — Upload a CSV file to create multiple QR codes at once.

### QR Code Detail & Sub-Features (replace {id} with actual QR code ID)
- **QR Detail** → `/qr/{id}` — View full details of a specific QR code.
- **Edit QR** → `/qr/{id}/edit` — Change the target URL, colors, logo, style of an existing QR code.
- **Auto-Rotate** → `/qr/{id}/rotation` — Set up automatic URL rotation so the QR code cycles through multiple destination URLs.
  *Example:* Add 3 URLs and the QR code will rotate between them evenly or by weight.
- **Multi-Language** → `/qr/{id}/languages` — Serve different destination URLs based on the scanner's browser language.
  *Example:* English users go to /en page, Spanish users go to /es page.
- **Time Rules** → `/qr/{id}/time-rules` — Redirect to different URLs based on time of day or day of week.
  *Example:* Lunch menu URL from 11am-2pm, dinner menu URL from 5pm-10pm.
- **Device Rules** → `/qr/{id}/device-rules` — Redirect based on the scanner's device type (mobile, tablet, desktop).
- **Geo-Fence** → `/qr/{id}/geo-fence` — Redirect based on the scanner's geographic location.
  *Example:* US users see USD pricing page, EU users see EUR pricing page.
- **A/B Test** → `/qr/{id}/ab-test` — Split traffic between multiple URLs to test which performs better.
  *Example:* Send 50% of scans to landing page A and 50% to landing page B, then compare conversion rates.
- **Deep Link** → `/qr/{id}/deep-link` — Configure deep links that open specific content inside mobile apps (iOS/Android).
- **PDF Viewer** → `/qr/{id}/pdf-viewer` — Attach a PDF that opens in a built-in viewer when the QR code is scanned.
- **Video Player** → `/qr/{id}/video-player` — Attach a video that plays in a built-in player when scanned.
- **vCard** → `/qr/{id}/vcard` — Create a digital business card (vCard) that scanners can save to their contacts.
- **Doc Upload** → `/qr/{id}/doc-upload` — Upload documents (PDF, images, etc.) that are served when the QR code is scanned.
- **Funnel** → `/qr/{id}/funnel` — Set up a multi-step redirect funnel with multiple pages in sequence.
- **Poster Designer** → `/qr/{id}/poster` — Design a professional poster with your QR code embedded, ready to print.
- **Link Analytics** → `/qr/{id}/link-analytics` — View click analytics for specific links associated with this QR code.
- **Scan Alerts** → `/qr/{id}/scan-alerts` — Get email or webhook notifications when your QR code is scanned.
  *Example:* Receive an email every time someone scans your event QR code.
- **Loyalty Program** → `/qr/{id}/loyalty` — Set up a stamp/points loyalty program tied to QR code scans.
- **Token Redirect** → `/qr/{id}/token-redirect` — Generate unique one-time-use scan tokens for secure redirects.
- **Expiry Settings** → `/qr/{id}/expiry` — Set an expiration date/scan limit for the QR code.
  *Example:* QR code expires after 100 scans or after December 31st.
- **Product Authentication** → `/qr/{id}/product-auth` — Use QR codes for product verification and anti-counterfeiting.
- **Access Control** → `/qr/{id}/access` — Restrict who can access the QR code's destination (password, email whitelist).
- **Version History** → `/qr/{id}/versions` — View and restore previous versions of QR code settings.

### Analytics
- **Analytics Dashboard** → `/analytics` — Comprehensive analytics: total scans, unique visitors, top QR codes, geographic data, device breakdown, time trends.
- **Per-QR Analytics** → `/analytics/qr/{id}` — Detailed analytics for a specific QR code.

### Automations
- **Automations** → `/automations` — Create automated workflows triggered by QR code events (scans, thresholds, schedules).
  *Example:* Automatically send a welcome email when a QR code is scanned for the first time.

### Landing Pages
- **Landing Pages List** → `/landing-pages` — View and manage all your landing pages.
- **Page Builder** → `/pages/builder` — Visual drag-and-drop landing page builder.
- **AI Page Generator** → `/pages/ai-generator` — Describe your page in plain English and AI generates a beautiful, animated landing page instantly.
  *Example:* Type "A product launch page for wireless earbuds with a hero section, features, and pricing" and get a complete page.

### Forms
- **Forms List** → `/forms` — View and manage all forms.
- **Create Form** → `/forms/create` — Build custom forms with various field types (text, email, select, checkbox, etc.).
- **Form + Landing Page Wizard** → `/forms/create-with-page` — Create a form and an AI-generated landing page together, automatically linked.
- **Form Submissions** → `/forms/{id}/submissions` — View all submissions received for a specific form.

### Popups
- **Popups List** → `/popups` — View and manage popup campaigns.
- **Create Popup** → `/popups/create` — Design popups to show on your landing pages for lead capture, announcements, etc.

### Settings
- **Settings** → `/settings` — General account and organization settings.
- **Team Management** → `/settings/team` — Invite team members, assign roles (Admin, Editor, Viewer).
- **API Keys** → `/settings/api-keys` — Generate and manage API keys for programmatic access.
- **Webhooks** → `/settings/webhooks` — Configure webhook endpoints to receive real-time event notifications.
- **Audit Log** → `/settings/audit-log` — View a complete log of all actions taken in your organization.

## Response Guidelines
1. ONLY answer questions about QRGenie. For unrelated questions, say: "I'm QRGenie AI Assistant and I can only help with QRGenie features. Is there anything about QRGenie I can help you with?"
2. When mentioning a feature, always include the navigation path in format: **Go to → `/path`**
3. Provide practical examples with step-by-step instructions when explaining features.
4. Be concise but thorough. Use bullet points and formatting for clarity.
5. If a user wants to do something, identify which QRGenie feature can help and guide them to it.
6. Be friendly, professional, and encouraging."""

    def post(self, request):
        message = request.data.get('message', '').strip()
        history = request.data.get('history', [])

        if not message:
            return Response({'error': 'Message is required.'}, status=status.HTTP_400_BAD_REQUEST)

        import requests as http_requests
        import logging
        from decouple import config as env_config

        logger = logging.getLogger('qrgenie')

        groq_key = env_config('GROQ_API_KEY', default='')
        if not groq_key:
            logger.error('[AI Chat] GROQ_API_KEY not found')
            return Response({'error': 'AI service not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        messages = [{'role': 'system', 'content': self.SYSTEM_PROMPT}]

        # Add conversation history (limit to last 20 messages to stay within context)
        if isinstance(history, list):
            for h in history[-20:]:
                role = h.get('role', '')
                content = h.get('content', '')
                if role in ('user', 'assistant') and content:
                    messages.append({'role': role, 'content': content})

        messages.append({'role': 'user', 'content': message})

        try:
            logger.info('[AI Chat] Sending request to Groq API...')
            resp = http_requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {groq_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'llama-3.3-70b-versatile',
                    'messages': messages,
                    'temperature': 0.7,
                    'max_tokens': 1024,
                },
                timeout=30,
            )
            logger.info(f'[AI Chat] Groq response status: {resp.status_code}')
            if resp.status_code != 200:
                logger.error(f'[AI Chat] Groq error body: {resp.text[:500]}')
            resp.raise_for_status()
            data = resp.json()
            reply = data['choices'][0]['message']['content']
            return Response({'reply': reply})
        except http_requests.exceptions.Timeout:
            logger.error('[AI Chat] Groq API timed out')
            return Response({'error': 'AI service timed out. Please try again.'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except Exception as e:
            logger.error(f'[AI Chat] Exception: {type(e).__name__}: {e}')
            return Response({'error': f'AI service error: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)
