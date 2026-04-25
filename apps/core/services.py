"""
Service Registry
=================
Modular service layer enabling independent scaling of QRGenie components.

Each service is a self-contained module with:
  - name, description, health endpoint
  - can be deployed independently as a microservice
  - communicates via REST or shared database

In monolith mode (current), all services run in one Django process.
In microservice mode, each service runs as a separate container
with its own Gunicorn workers, pointed at the same database.
"""


class ServiceDefinition:
    """Describes a deployable service unit."""
    __slots__ = ('name', 'app_label', 'description', 'url_prefix', 'scalable_independently')

    def __init__(self, name, app_label, description, url_prefix, scalable_independently=True):
        self.name = name
        self.app_label = app_label
        self.description = description
        self.url_prefix = url_prefix
        self.scalable_independently = scalable_independently

    def __repr__(self):
        return f"<Service: {self.name}>"


# ── Service Catalog ────────────────────────────────────
# These map 1:1 to Django apps and can be extracted into
# separate containers by running gunicorn with URL prefixes.

SERVICES = {
    'redirect': ServiceDefinition(
        name='redirect',
        app_label='qrcodes',
        description='QR scan redirect engine — highest throughput, stateless, cacheable',
        url_prefix='/r/',
        scalable_independently=True,
    ),
    'api': ServiceDefinition(
        name='api',
        app_label='qrcodes',
        description='REST API for QR CRUD, settings, management',
        url_prefix='/api/v1/qr/',
        scalable_independently=True,
    ),
    'analytics': ServiceDefinition(
        name='analytics',
        app_label='analytics',
        description='Scan analytics, dashboards, exports — read-heavy',
        url_prefix='/api/v1/analytics/',
        scalable_independently=True,
    ),
    'automation': ServiceDefinition(
        name='automation',
        app_label='automation',
        description='Webhooks, scheduled tasks, event triggers',
        url_prefix='/api/v1/automation/',
        scalable_independently=True,
    ),
    'ai': ServiceDefinition(
        name='ai',
        app_label='ai_service',
        description='AI-powered QR suggestions, content generation',
        url_prefix='/api/v1/ai/',
        scalable_independently=True,
    ),
    'landing_pages': ServiceDefinition(
        name='landing_pages',
        app_label='landing_pages',
        description='Landing page builder and renderer',
        url_prefix='/api/v1/landing-pages/',
        scalable_independently=True,
    ),
    'forms': ServiceDefinition(
        name='forms',
        app_label='forms_builder',
        description='Form builder and submission handler',
        url_prefix='/api/v1/forms/',
        scalable_independently=True,
    ),
    'core': ServiceDefinition(
        name='core',
        app_label='core',
        description='Auth, organizations, users, audit logs — shared foundation',
        url_prefix='/api/v1/',
        scalable_independently=False,
    ),
}


def get_service(name: str) -> ServiceDefinition:
    return SERVICES[name]


def list_services():
    return list(SERVICES.values())
