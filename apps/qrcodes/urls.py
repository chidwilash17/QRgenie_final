from django.urls import path
from .views import (
    QRCodeListCreateView, QRCodeDetailView,
    QRCodeArchiveView, QRCodeRestoreView, QRCodePauseView, QRCodeFreezeView,
    RoutingRuleListCreateView, RoutingRuleDetailView,
    MultiLinkListCreateView, MultiLinkDetailView,
    FileUploadView, QRCodeDownloadImageView, QRCodeExportZipView,
    QRLogoUploadView,
    BulkUploadView, BulkUploadJobStatusView,
    QRPasswordVerifyView,
    QRVersionListView, QRVersionRestoreView,
    RotationScheduleView,
    LanguageRouteView,
    TimeScheduleView,
    PDFDocumentView,
    VideoDocumentView,
    DeviceRouteView,
    GeoFenceRuleView,
    ABTestView,
    DeepLinkView,
    TokenRedirectView,
    QRExpiryView,
    ScanAlertView,
    LoyaltyProgramView,
    LoyaltyMembersView,
    LoyaltyScanView,
    DigitalVCardView, VCardDownloadView,
    ProductAuthView, ProductSerialListView, ProductSerialGenerateView, ProductVerifyView,
    DocUploadFormView, DocSubmissionsListView, DocPublicUploadView,
    FunnelConfigView, FunnelStepListView, FunnelPublicView, FunnelTrackView, FunnelSessionsView,
    QRAccessListView, QRMyAccessView,
    PosterPresetsView, PosterGenerateView,
    FeatureStatusView, SimulateRedirectView,
)
from .redirect_views import GeoDebugView, MyLocationView

urlpatterns = [
    # QR CRUD
    path('', QRCodeListCreateView.as_view(), name='qr-list-create'),
    path('<uuid:id>/', QRCodeDetailView.as_view(), name='qr-detail'),

    # Status management
    path('<uuid:id>/archive/', QRCodeArchiveView.as_view(), name='qr-archive'),
    path('<uuid:id>/restore/', QRCodeRestoreView.as_view(), name='qr-restore'),
    path('<uuid:id>/pause/', QRCodePauseView.as_view(), name='qr-pause'),
    path('<uuid:id>/freeze/', QRCodeFreezeView.as_view(), name='qr-freeze'),

    # Routing rules
    path('<uuid:qr_id>/rules/', RoutingRuleListCreateView.as_view(), name='qr-rules'),
    path('<uuid:qr_id>/rules/<uuid:id>/', RoutingRuleDetailView.as_view(), name='qr-rule-detail'),

    # Multi-link management
    path('<uuid:qr_id>/links/', MultiLinkListCreateView.as_view(), name='qr-links'),
    path('<uuid:qr_id>/links/<uuid:id>/', MultiLinkDetailView.as_view(), name='qr-link-detail'),

    # File upload
    path('<uuid:qr_id>/files/', FileUploadView.as_view(), name='qr-files'),

    # Logo upload
    path('logo-upload/', QRLogoUploadView.as_view(), name='qr-logo-upload'),

    # Download & Export
    path('<uuid:id>/generate-image/', QRCodeDownloadImageView.as_view(), name='qr-download'),
    path('export/', QRCodeExportZipView.as_view(), name='qr-export-zip'),

    # Bulk upload
    path('bulk-upload/', BulkUploadView.as_view(), name='qr-bulk-upload'),
    path('bulk-upload/<uuid:id>/', BulkUploadJobStatusView.as_view(), name='qr-bulk-status'),

    # Password verification
    path('<uuid:id>/verify-password/', QRPasswordVerifyView.as_view(), name='qr-verify-password'),

    # Version history
    path('<uuid:qr_id>/versions/', QRVersionListView.as_view(), name='qr-versions'),
    path('<uuid:qr_id>/versions/<uuid:version_id>/restore/', QRVersionRestoreView.as_view(), name='qr-version-restore'),

    # Auto-rotating landing pages (Feature 6)
    path('<uuid:id>/rotation/', RotationScheduleView.as_view(), name='qr-rotation'),

    # Multi-language auto-detection (Feature 8)
    path('<uuid:id>/languages/', LanguageRouteView.as_view(), name='qr-languages'),

    # Time-based redirects (Feature 9)
    path('<uuid:id>/time-rules/', TimeScheduleView.as_view(), name='qr-time-rules'),

    # PDF Viewer (Feature 11)
    path('<uuid:id>/pdf/', PDFDocumentView.as_view(), name='qr-pdf'),

    # Video Player (Feature 13)
    path('<uuid:id>/video/', VideoDocumentView.as_view(), name='qr-video'),

    # Device-based redirect (Feature 15)
    path('<uuid:id>/device-routes/', DeviceRouteView.as_view(), name='qr-device-routes'),

    # GPS-Radius Geo-Fence (Feature 17)
    path('<uuid:id>/geo-fence/', GeoFenceRuleView.as_view(), name='qr-geo-fence'),

    # A/B Split Testing (Feature 18)
    path('<uuid:id>/ab-test/', ABTestView.as_view(), name='qr-ab-test'),

    # App Deep Linking (Feature 19)
    path('<uuid:id>/deep-link/', DeepLinkView.as_view(), name='qr-deep-link'),

    # Short-Lived Token Redirect (Feature 20)
    path('<uuid:id>/token-redirect/', TokenRedirectView.as_view(), name='qr-token-redirect'),

    # Expiry-Based QR (Feature 21)
    path('<uuid:id>/expiry/', QRExpiryView.as_view(), name='qr-expiry'),

    # Scan Alerts (Feature 25)
    path('<uuid:id>/scan-alert/', ScanAlertView.as_view(), name='qr-scan-alert'),

    # Loyalty Point QR (Feature 26)
    path('<uuid:id>/loyalty/', LoyaltyProgramView.as_view(), name='qr-loyalty'),
    path('<uuid:id>/loyalty/members/', LoyaltyMembersView.as_view(), name='qr-loyalty-members'),
    path('<uuid:id>/loyalty/scan/', LoyaltyScanView.as_view(), name='qr-loyalty-scan'),

    # Digital vCard QR (Feature 28)
    path('<uuid:id>/vcard/', DigitalVCardView.as_view(), name='qr-vcard'),
    path('<uuid:id>/vcard/download/', VCardDownloadView.as_view(), name='qr-vcard-download'),

    # Product Authentication QR (Feature 31)
    path('<uuid:id>/product-auth/', ProductAuthView.as_view(), name='qr-product-auth'),
    path('<uuid:id>/product-auth/serials/', ProductSerialListView.as_view(), name='qr-product-serials'),
    path('<uuid:id>/product-auth/generate/', ProductSerialGenerateView.as_view(), name='qr-product-generate'),
    path('<uuid:id>/product-auth/verify/', ProductVerifyView.as_view(), name='qr-product-verify'),

    # Document Upload Form (Feature 33)
    path('<uuid:id>/doc-upload/', DocUploadFormView.as_view(), name='qr-doc-upload-form'),
    path('<uuid:id>/doc-upload/submissions/', DocSubmissionsListView.as_view(), name='qr-doc-submissions'),
    path('<uuid:id>/doc-upload/public/', DocPublicUploadView.as_view(), name='qr-doc-public-upload'),

    # Funnel Pages (Feature 34)
    path('<uuid:id>/funnel/', FunnelConfigView.as_view(), name='qr-funnel-config'),
    path('<uuid:id>/funnel/steps/', FunnelStepListView.as_view(), name='qr-funnel-steps'),
    path('<uuid:id>/funnel/public/', FunnelPublicView.as_view(), name='qr-funnel-public'),
    path('<uuid:id>/funnel/track/', FunnelTrackView.as_view(), name='qr-funnel-track'),
    path('<uuid:id>/funnel/sessions/', FunnelSessionsView.as_view(), name='qr-funnel-sessions'),

    # Role-Based QR Access (Feature 36)
    path('<uuid:id>/access/', QRAccessListView.as_view(), name='qr-access-list'),
    path('<uuid:id>/access/me/', QRMyAccessView.as_view(), name='qr-access-me'),

    # Poster Generator (Feature 45)
    path('poster-presets/', PosterPresetsView.as_view(), name='poster-presets'),
    path('<uuid:id>/poster/', PosterGenerateView.as_view(), name='qr-poster-generate'),

    # GeoIP debug — shows what city/region is detected for your IP
    path('geo-debug/', GeoDebugView.as_view(), name='geo-debug'),

    # Dashboard map — returns requester's lat/lng via IP geolocation
    path('my-location/', MyLocationView.as_view(), name='my-location'),

    # Feature Conflict Detection & Simulation
    path('<uuid:id>/feature-status/', FeatureStatusView.as_view(), name='qr-feature-status'),
    path('<uuid:id>/simulate/', SimulateRedirectView.as_view(), name='qr-simulate'),
]