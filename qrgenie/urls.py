"""
QRGenie URL Configuration
==========================
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.views.static import serve as static_serve
from django.http import HttpResponse
from apps.core.health import HealthCheckView
from apps.core.admin_2fa import admin_2fa_setup_view, admin_2fa_verify_view
from decouple import config as env_config
import re


FRONTEND_DIST = settings.BASE_DIR.parent / 'frontend' / 'dist'

# Admin URL is configurable via env — hide it from automated scanners.
# Set DJANGO_ADMIN_URL=secret-mgmt-path/ in production.
DJANGO_ADMIN_URL = env_config('DJANGO_ADMIN_URL', default='admin/')

urlpatterns = [
    # Health probe — no auth, no middleware overhead
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Robots.txt — disallow crawlers from API and internal paths
    path('robots.txt', lambda r: HttpResponse(
        'User-agent: *\n'
        'Disallow: /api/\n'
        'Disallow: /r/\n'
        'Disallow: /pdf/\n'
        'Disallow: /video/\n'
        'Disallow: /popup/\n',
        content_type='text/plain',
    ), name='robots-txt'),

    # Admin 2FA gates (must be before admin.site.urls)
    path(f'{DJANGO_ADMIN_URL}2fa/setup/', admin_2fa_setup_view, name='admin-2fa-setup'),
    path(f'{DJANGO_ADMIN_URL}2fa/verify/', admin_2fa_verify_view, name='admin-2fa-verify'),

    path(DJANGO_ADMIN_URL, admin.site.urls),

    # API v1
    path('api/v1/auth/', include('apps.core.urls.auth_urls')),
    path('api/v1/users/', include('apps.core.urls.user_urls')),
    path('api/v1/organizations/', include('apps.core.urls.org_urls')),
    path('api/v1/qr/', include('apps.qrcodes.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/automation/', include('apps.automation.urls')),
    path('api/v1/ai/', include('apps.ai_service.urls')),
    path('api/v1/landing-pages/', include('apps.landing_pages.urls')),
    path('api/v1/webhooks/', include('apps.webhooks.urls')),
    path('api/v1/forms/', include('apps.forms_builder.urls')),
    path('api/v1/public/forms/', include('apps.forms_builder.public_urls')),
    path('api/v1/popups/', include('apps.landing_pages.popup_urls')),

    # Developer REST API (API key auth)
    path('api/v1/developer/', include('apps.qrcodes.api_urls')),

    # Redirect engine (short URL)
    path('r/<str:slug>/', include('apps.qrcodes.redirect_urls')),

    # PDF viewer (public, token-secured — Feature 11)
    path('pdf/<uuid:token>/', include('apps.qrcodes.pdf_urls')),

    # Video player (public, token-secured — Feature 13)
    path('video/<uuid:token>/', include('apps.qrcodes.video_urls')),

    # Popup embed (public — Feature 14)
    path('popup/<uuid:token>/', include('apps.landing_pages.popup_public_urls')),

    # Landing page public render (verify / download / event sub-routes)
    path('p/', include('apps.landing_pages.public_urls')),

    # Public form fill — serve React SPA index.html so the frontend router handles it
    path('f/<str:slug>/', TemplateView.as_view(template_name='index.html')),

    # Serve Vite build static assets (JS/CSS/images) through Django
    path('assets/<path:path>', static_serve, {'document_root': FRONTEND_DIST / 'assets'}),
    path('vite.svg', static_serve, {'document_root': FRONTEND_DIST, 'path': 'vite.svg'}),

    # Catch-all: serve React SPA for any frontend route (must be LAST)
    # Dynamically excludes the (randomized) admin URL so it is never swallowed.
    re_path(
        rf'^(?!api/|{re.escape(DJANGO_ADMIN_URL)}|media/|static/|r/|p/|pdf/|video/|popup/|health/).*$',
        TemplateView.as_view(template_name='index.html'),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
