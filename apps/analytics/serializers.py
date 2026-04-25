"""
Analytics Serializers
======================
"""
from rest_framework import serializers
from .models import ScanEvent, DailyMetric, LinkClickEvent, ConversionEvent


class ScanEventSerializer(serializers.ModelSerializer):
    qr_slug = serializers.CharField(source='qr_code.slug', read_only=True)

    class Meta:
        model = ScanEvent
        fields = [
            'id', 'qr_code', 'qr_slug', 'ip_address', 'country', 'city',
            'device_type', 'os', 'browser', 'language', 'referrer',
            'destination_url', 'rule_matched', 'is_unique', 'tags', 'scanned_at',
        ]


class DailyMetricSerializer(serializers.ModelSerializer):
    qr_slug = serializers.CharField(source='qr_code.slug', read_only=True)

    class Meta:
        model = DailyMetric
        fields = [
            'id', 'qr_code', 'qr_slug', 'date', 'total_scans', 'unique_scans',
            'country_breakdown', 'device_breakdown', 'browser_breakdown',
            'os_breakdown', 'hourly_breakdown', 'referrer_breakdown', 'link_clicks',
        ]


class LinkClickEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LinkClickEvent
        fields = ['id', 'qr_code', 'link_url', 'link_label', 'country', 'device_type', 'clicked_at']


class AnalyticsSummarySerializer(serializers.Serializer):
    """Serializer for org-wide analytics summary."""
    total_scans = serializers.IntegerField()
    unique_scans = serializers.IntegerField()
    total_qr_codes = serializers.IntegerField()
    scans_today = serializers.IntegerField()
    scans_this_week = serializers.IntegerField()
    scans_this_month = serializers.IntegerField()
    top_countries = serializers.ListField()
    top_devices = serializers.ListField()
    top_qr_codes = serializers.ListField()
    daily_trend = serializers.ListField()


class ConversionEventSerializer(serializers.ModelSerializer):
    qr_slug = serializers.CharField(source='qr_code.slug', read_only=True)

    class Meta:
        model = ConversionEvent
        fields = [
            'id', 'qr_code', 'qr_slug', 'event_type', 'event_label',
            'event_value', 'metadata', 'country', 'device_type', 'session_id',
            'created_at',
        ]
