from django.urls import path
from .views import (
    WebhookEndpointListCreateView,
    WebhookEndpointDetailView,
    WebhookEndpointToggleView,
    WebhookEndpointTestView,
    WebhookDeliveryListView,
    WebhookDeliveryRetryView,
)

app_name = 'webhooks'

urlpatterns = [
    path('', WebhookEndpointListCreateView.as_view(), name='list-create'),
    path('<uuid:id>/', WebhookEndpointDetailView.as_view(), name='detail'),
    path('<uuid:id>/toggle/', WebhookEndpointToggleView.as_view(), name='toggle'),
    path('<uuid:id>/test/', WebhookEndpointTestView.as_view(), name='test'),
    path('<uuid:endpoint_id>/deliveries/', WebhookDeliveryListView.as_view(), name='deliveries'),
    path('deliveries/<uuid:delivery_id>/retry/', WebhookDeliveryRetryView.as_view(), name='delivery-retry'),
]
