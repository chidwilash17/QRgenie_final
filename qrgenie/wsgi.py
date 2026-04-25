import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qrgenie.settings')
application = get_wsgi_application()

# Auto-apply pending migrations on startup (safe for single-server PythonAnywhere)
try:
    from django.core.management import call_command
    call_command('migrate', '--no-input', verbosity=0)
except Exception:
    pass




