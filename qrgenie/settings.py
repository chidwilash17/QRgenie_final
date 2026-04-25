"""
QRGenie Django Settings
========================
Enterprise-grade QR management platform.
"""

import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ───────────────────────────────────────────
SECRET_KEY = config('DJANGO_SECRET_KEY', default='dev-secret-key-change-in-prod')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*' if DEBUG else '', cast=Csv())

# Hard-fail in production if secrets are still set to insecure defaults
if not DEBUG:
    if SECRET_KEY in ('dev-secret-key-change-in-prod', ''):
        raise RuntimeError(
            'DJANGO_SECRET_KEY must be set to a strong random value in production. '
            'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
        )
    if not ALLOWED_HOSTS or ALLOWED_HOSTS == ['*']:
        raise RuntimeError(
            'ALLOWED_HOSTS must be explicitly set in production (e.g. ALLOWED_HOSTS=yourdomain.com). '
            'Wildcard "*" is not permitted.'
        )

# ── Application Definition ─────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',  # required for BLACKLIST_AFTER_ROTATION
    'corsheaders',
    'django_filters',
    'django_celery_beat',
    # QRGenie apps
    'apps.core',
    'apps.qrcodes',
    'apps.analytics',
    'apps.automation',
    'apps.ai_service',
    'apps.landing_pages',
    'apps.webhooks',
    'apps.forms_builder',
]

MIDDLEWARE = [
    'apps.core.middleware.RateLimitMiddleware',       # Must be first — reject abusers before any work
    'django.middleware.security.SecurityMiddleware',
    'apps.core.middleware.SecurityHeadersMiddleware', # OWASP headers on every response
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.Admin2FAMiddleware',              # 2FA gate for admin panel
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.RequestLoggingMiddleware',
    'apps.core.middleware.OrganizationMiddleware',
]

ROOT_URLCONF = 'qrgenie.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'qrgenie.wsgi.application'
AUTH_USER_MODEL = 'core.User'

# ── Database (SQLite3 for development) ─────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Cache ─────────────────────────────────────────────
# Redis when available, database cache otherwise (works on PythonAnywhere)
REDIS_URL = config('REDIS_URL', default='')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    # Database cache — persistent, multi-process safe, no external deps.
    # Run: python manage.py createcachetable  (once, on first deploy)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'qrgenie_cache',
        }
    }

# ── Password Validation ───────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalization ──────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static & Media Files ─────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Upload size limits (DoS protection) ───────────────
# Max in-memory size before Django spools to disk (default: 2.5 MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB
# Max total request body size (guards against huge multi-part POST abuse)
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # 15 MB
# Max number of form fields in a single POST (prevents hash-flood attacks)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

# Allow Google Sign-In popup to communicate back to the page
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# ── Clerk Authentication ──────────────────────────────
CLERK_JWKS_URL = config('CLERK_JWKS_URL', default='https://proud-dove-84.clerk.accounts.dev/.well-known/jwks.json')
CLERK_SECRET_KEY = config('CLERK_SECRET_KEY', default='')

# ── Django REST Framework ─────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # Email/password JWT
        'apps.core.clerk_auth.ClerkAuthentication',  # Clerk social login JWT
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '500/hour',
        'user': '5000/hour',
        'login': '5/minute',          # brute-force protection on /auth/login/
        'register': '10/hour',        # account-creation spam protection
        'password_reset': '5/hour',   # email enumeration protection
        'scan': '500/minute',         # QR scan redirect (high-traffic public endpoint)
    },
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# ── JWT Configuration ─────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,   # old refresh tokens are invalidated on rotation
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_OBTAIN_SERIALIZER': 'apps.core.serializers.CustomTokenObtainPairSerializer',
}

# ── CORS ──────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = False  # Never allow all — explicit whitelist only
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173' if DEBUG else '',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173' if DEBUG else '',
    cast=Csv()
)

# ── Proxy / AWS ALB ───────────────────────────────────
# Set NUM_PROXIES=1 when behind AWS ALB / nginx so the real client IP
# is read from X-Forwarded-For instead of REMOTE_ADDR.
# Without this, rate limiting and audit logs are IP-spoofable.
NUM_PROXIES = config('NUM_PROXIES', default=0, cast=int)

# ── Celery Configuration ─────────────────────────────
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=REDIS_URL or 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = REDIS_URL or config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_TASK_ALWAYS_EAGER = not bool(REDIS_URL)  # Run tasks synchronously if no Redis
CELERY_TASK_EAGER_PROPAGATES = True
# Short timeouts so broker connection failures never block web requests
CELERY_BROKER_CONNECTION_TIMEOUT = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False
CELERY_REDIS_SOCKET_CONNECT_TIMEOUT = 1
CELERY_REDIS_SOCKET_TIMEOUT = 1
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# ── MinIO / S3 Configuration ─────────────────────────
MINIO_ENDPOINT = config('MINIO_ENDPOINT', default='localhost:9000')
MINIO_ACCESS_KEY = config('MINIO_ACCESS_KEY', default='minioadmin')
MINIO_SECRET_KEY = config('MINIO_SECRET_KEY', default='minioadmin123')
MINIO_BUCKET = config('MINIO_BUCKET', default='qrgenie-assets')
MINIO_USE_SSL = config('MINIO_USE_SSL', default=False, cast=bool)

# ── OpenAI Configuration ─────────────────────────────
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
OPENAI_MODEL = config('OPENAI_MODEL', default='gpt-4o')

# ── GeoIP Configuration ──────────────────────────────
GEOIP_DB_PATH = config('GEOIP_DB_PATH', default=str(BASE_DIR / 'geoip' / 'GeoLite2-City.mmdb'))

# ── QR Configuration ─────────────────────────────────
QR_SLUG_LENGTH = 8
SITE_BASE_URL = config('SITE_BASE_URL', default='http://localhost:8000')
QR_BASE_REDIRECT_URL = config('QR_BASE_REDIRECT_URL', default=f'{SITE_BASE_URL}/r')

# ── Logging ───────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',  # rotates at 10 MB, keeps 5 backups
            'filename': BASE_DIR / 'logs' / 'qrgenie.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'WARNING',  # no sensitive request data in prod logs
            'propagate': False,
        },
    },
}

# Create logs directory
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# ── Email Config (SMTP) ───────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='QRGenie Alerts <noreply@qrgenie.io>')

# ── Rate Limiting (custom middleware) ─────────────────
# Redirect endpoint: per-IP, uses Django cache (no Redis needed)
REDIRECT_RATE_LIMIT = config('REDIRECT_RATE_LIMIT', default=120, cast=int)   # max requests
REDIRECT_RATE_WINDOW = config('REDIRECT_RATE_WINDOW', default=60, cast=int)  # per N seconds
# API endpoint: per-IP
API_RATE_LIMIT = config('API_RATE_LIMIT', default=600, cast=int)
API_RATE_WINDOW = config('API_RATE_WINDOW', default=60, cast=int)

# ── Production Security Hardening ─────────────────────
# These are active when DEBUG=False (production)
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_AGE = 60 * 60 * 24 * 7   # 7 days — explicit rather than Django's 2-week default
    SECURE_CONTENT_TYPE_NOSNIFF = True       # redundant with header middleware, belt-and-suspenders
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# ── Database ──────────────────────────────────────────
# Development: SQLite (default). Production: PostgreSQL via DATABASE_URL.
#   DATABASE_URL=postgres://user:pass@rds-host:5432/qrgenie
DATABASE_URL = config('DATABASE_URL', default='')
ALLOW_SQLITE_IN_PRODUCTION = config('ALLOW_SQLITE_IN_PRODUCTION', default=False, cast=bool)
if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
elif not DEBUG and not ALLOW_SQLITE_IN_PRODUCTION:
    raise RuntimeError(
        'DATABASE_URL must be set in production. '
        'SQLite is not safe for concurrent production workloads. '
        'Set DATABASE_URL=postgres://user:pass@host:5432/dbname'
    )

# ── AWS S3 Media Storage ──────────────────────────────
# Set USE_S3=True + AWS_* vars to store uploaded files in S3.
# In dev, files are stored locally under MEDIA_ROOT.
USE_S3 = config('USE_S3', default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID     = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME    = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN  = config('AWS_S3_CUSTOM_DOMAIN', default=f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com')
    AWS_DEFAULT_ACL       = 'private'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    DEFAULT_FILE_STORAGE  = 'storages.backends.s3boto3.S3Boto3Storage'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
