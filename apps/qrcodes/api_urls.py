"""
Developer REST API URL Configuration
======================================
/api/v1/developer/  —  API key authenticated endpoints
"""
from django.urls import path
from .api_views import (
    DevQRListCreateView, DevQRDetailView,
    DevQRAnalyticsView, DevQRBulkAnalyticsView,
    DevAPIInfoView,
)

urlpatterns = [
    # API info
    path('info/', DevAPIInfoView.as_view(), name='dev-api-info'),

    # QR CRUD
    path('qr/', DevQRListCreateView.as_view(), name='dev-qr-list-create'),
    path('qr/<uuid:id>/', DevQRDetailView.as_view(), name='dev-qr-detail'),

    # Analytics
    path('qr/<uuid:id>/analytics/', DevQRAnalyticsView.as_view(), name='dev-qr-analytics'),
    path('analytics/summary/', DevQRBulkAnalyticsView.as_view(), name='dev-analytics-summary'),
]
