from django.contrib import admin
from .models import QRCode, RoutingRule, MultiLinkItem, FileAttachment, PaymentConfig, ChatConfig, BulkUploadJob


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'qr_type', 'status', 'total_scans', 'organization', 'created_at']
    list_filter = ['qr_type', 'status']
    search_fields = ['title', 'slug', 'description']
    readonly_fields = ['id', 'slug', 'total_scans', 'unique_scans']


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ['qr_code', 'rule_type', 'priority', 'is_active', 'destination_url']
    list_filter = ['rule_type', 'is_active']


@admin.register(MultiLinkItem)
class MultiLinkItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'qr_code', 'url', 'click_count', 'sort_order']


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'qr_code', 'version', 'is_current', 'download_count']


@admin.register(BulkUploadJob)
class BulkUploadJobAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'organization', 'status', 'success_count', 'error_count', 'created_at']
    list_filter = ['status']
