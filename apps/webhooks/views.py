"""
Webhooks — Views
==================
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.permissions import IsOrgMember, IsOrgOwnerOrAdmin
from .models import WebhookEndpoint, WebhookDelivery
from .serializers import (
    WebhookEndpointSerializer,
    WebhookEndpointCreateSerializer,
    WebhookDeliverySerializer,
)


class WebhookEndpointListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/webhooks/
    POST /api/v1/webhooks/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return WebhookEndpointCreateSerializer
        return WebhookEndpointSerializer

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(organization=self.request.user.organization)


class WebhookEndpointDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/v1/webhooks/<id>/
    """
    serializer_class = WebhookEndpointSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(organization=self.request.user.organization)


class WebhookEndpointToggleView(APIView):
    """POST /api/v1/webhooks/<id>/toggle/ — Enable/disable."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, id):
        try:
            ep = WebhookEndpoint.objects.get(id=id, organization=request.user.organization)
        except WebhookEndpoint.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        ep.is_active = not ep.is_active
        if ep.is_active:
            ep.disabled_reason = ''
            ep.consecutive_failures = 0
        ep.save(update_fields=['is_active', 'disabled_reason', 'consecutive_failures', 'updated_at'])

        return Response({'id': str(ep.id), 'is_active': ep.is_active})


class WebhookEndpointTestView(APIView):
    """POST /api/v1/webhooks/<id>/test/ — Send a test ping."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, id):
        try:
            ep = WebhookEndpoint.objects.get(id=id, organization=request.user.organization)
        except WebhookEndpoint.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from .tasks import deliver_webhook
        deliver_webhook.delay(
            str(ep.id),
            'ping',
            {'event': 'ping', 'message': 'Test webhook from QRGenie', 'timestamp': str(__import__('django').utils.timezone.now())},
        )
        return Response({'detail': 'Test webhook dispatched.'})


class WebhookDeliveryListView(generics.ListAPIView):
    """
    GET /api/v1/webhooks/<endpoint_id>/deliveries/
    List delivery logs for an endpoint.
    """
    serializer_class = WebhookDeliverySerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def get_queryset(self):
        return WebhookDelivery.objects.filter(
            endpoint__id=self.kwargs['endpoint_id'],
            endpoint__organization=self.request.user.organization,
        )


class WebhookDeliveryRetryView(APIView):
    """POST /api/v1/webhooks/deliveries/<delivery_id>/retry/ — Retry a failed delivery."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, delivery_id):
        try:
            delivery = WebhookDelivery.objects.get(
                id=delivery_id,
                endpoint__organization=request.user.organization,
            )
        except WebhookDelivery.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from .tasks import deliver_webhook
        deliver_webhook.delay(str(delivery.endpoint_id), delivery.event_type, delivery.payload)
        return Response({'detail': 'Retry dispatched.'})
