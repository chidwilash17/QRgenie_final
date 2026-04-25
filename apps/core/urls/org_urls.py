from django.urls import path
from apps.core.views import (
    OrganizationDetailView, OrganizationStatsView,
    APIKeyListCreateView, APIKeyRevokeView,
    AuditLogListView,
)

urlpatterns = [
    path('current/', OrganizationDetailView.as_view(), name='org-detail'),
    path('stats/', OrganizationStatsView.as_view(), name='org-stats'),
    path('api-keys/', APIKeyListCreateView.as_view(), name='org-api-keys'),
    path('api-keys/<uuid:id>/', APIKeyRevokeView.as_view(), name='org-api-key-revoke'),
    path('audit-logs/', AuditLogListView.as_view(), name='org-audit-logs'),
]
