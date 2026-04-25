from django.contrib import admin
from .models import WebhookEndpoint, WebhookDelivery


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['url', 'organization', 'is_active', 'consecutive_failures', 'created_at']
    list_filter = ['is_active']
    search_fields = ['url', 'description']


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['id', 'endpoint', 'event_type', 'status', 'response_status_code', 'attempt', 'delivered_at']
    list_filter = ['status', 'event_type']
    date_hierarchy = 'delivered_at'
