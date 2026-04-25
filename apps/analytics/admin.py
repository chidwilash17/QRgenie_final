from django.contrib import admin
from .models import ScanEvent, DailyMetric, LinkClickEvent


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'qr_code', 'ip_address', 'country', 'device_type', 'is_unique', 'scanned_at']
    list_filter = ['device_type', 'country', 'is_unique', 'scanned_at']
    search_fields = ['ip_address', 'qr_code__title', 'qr_code__slug']
    readonly_fields = ['id', 'fingerprint']
    date_hierarchy = 'scanned_at'


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = ['id', 'qr_code', 'date', 'total_scans', 'unique_scans', 'link_clicks']
    list_filter = ['date']
    search_fields = ['qr_code__title']
    date_hierarchy = 'date'


@admin.register(LinkClickEvent)
class LinkClickEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'qr_code', 'link_url', 'link_label', 'device_type', 'clicked_at']
    list_filter = ['device_type', 'clicked_at']
    search_fields = ['link_url', 'link_label']
    date_hierarchy = 'clicked_at'
