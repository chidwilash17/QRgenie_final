# WSGI config for QrGenie
import os
import sys

project_home = '/home/QrGenie/backend'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'qrgenie.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
