from rest_framework import serializers
from .models import WebhookEndpoint, WebhookDelivery
import ipaddress
from urllib.parse import urlparse


# Private / link-local IP prefixes an attacker could use for SSRF
_BLOCKED_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '0.0.0.0'})


class WebhookEndpointSerializer(serializers.ModelSerializer):
    delivery_count = serializers.IntegerField(source='deliveries.count', read_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = [
            'id', 'url', 'description', 'events', 'is_active',
            'custom_headers', 'consecutive_failures', 'last_failure_at',
            'disabled_reason', 'delivery_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'consecutive_failures', 'last_failure_at',
                            'disabled_reason', 'created_at', 'updated_at']


class WebhookEndpointCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ['url', 'description', 'events', 'custom_headers']

    def validate_url(self, value):
        """Block SSRF: reject localhost, private IPs, and non-HTTP(S) schemes."""
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https'):
            raise serializers.ValidationError('Webhook URL must use HTTP or HTTPS.')
        host = (parsed.hostname or '').lower()
        if host in _BLOCKED_HOSTS:
            raise serializers.ValidationError('Webhook URL cannot target localhost.')
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise serializers.ValidationError(
                    'Webhook URL cannot target a private or reserved IP address.'
                )
        except ValueError:
            pass  # hostname (not a bare IP) — fine
        return value

    def validate_events(self, value):
        valid = [c[0] for c in WebhookEndpoint.EVENT_CHOICES]
        for ev in value:
            if ev not in valid:
                raise serializers.ValidationError(f'Invalid event: {ev}. Valid: {valid}')
        return value

    def create(self, validated_data):
        request = self.context['request']
        return WebhookEndpoint.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'endpoint', 'event_type', 'status', 'payload',
            'response_status_code', 'response_body', 'attempt',
            'max_attempts', 'error_message', 'duration_ms', 'delivered_at',
        ]
