import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()
from apps.core.models import Organization
updated = Organization.objects.all().update(max_ai_tokens_per_month=500000)
print(f'Updated {updated} organizations to 500K tokens')
