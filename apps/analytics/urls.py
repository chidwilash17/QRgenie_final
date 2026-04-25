from django.urls import path
from .views import (
    AnalyticsSummaryView,
    QRAnalyticsView,
    ScanEventListView,
    DailyMetricListView,
    LinkClickTrackView,
    LinkClickAnalyticsView,
    ScanMapView,
    ScanMapDebugView,
    BackfillLocationsView,
    ConversionTrackView,
    ConversionAnalyticsView,
)

app_name = 'analytics'

urlpatterns = [
    path('summary/', AnalyticsSummaryView.as_view(), name='summary'),
    path('qr/<uuid:qr_id>/', QRAnalyticsView.as_view(), name='qr-analytics'),
    path('qr/<uuid:qr_id>/link-clicks/', LinkClickAnalyticsView.as_view(), name='qr-link-clicks'),
    path('qr/<uuid:qr_id>/conversions/', ConversionAnalyticsView.as_view(), name='qr-conversions'),
    path('qr/<uuid:qr_id>/scan-map/', ScanMapView.as_view(), name='qr-scan-map'),
    path('qr/<uuid:qr_id>/scan-map/debug/', ScanMapDebugView.as_view(), name='qr-scan-map-debug'),
    path('backfill-locations/', BackfillLocationsView.as_view(), name='backfill-locations'),
    path('events/', ScanEventListView.as_view(), name='scan-events'),
    path('daily/', DailyMetricListView.as_view(), name='daily-metrics'),
    path('click/', LinkClickTrackView.as_view(), name='link-click-track'),
    path('conversion/', ConversionTrackView.as_view(), name='conversion-track'),
]
