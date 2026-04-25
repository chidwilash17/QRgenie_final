from django.urls import path
from .views import (
    AutomationListCreateView,
    AutomationDetailView,
    AutomationToggleView,
    AutomationTestView,
    AutomationRunListView,
    ConditionListCreateView,
    ActionListCreateView,
    QRScheduleListCreateView,
    QRScheduleDetailView,
    QRScheduleToggleView,
    QRScheduleRunNowView,
    ExternalHookListCreateView,
    ExternalHookDetailView,
    ExternalHookTestView,
)

app_name = 'automation'

urlpatterns = [
    # Core automation CRUD
    path('', AutomationListCreateView.as_view(), name='list-create'),
    path('<uuid:id>/', AutomationDetailView.as_view(), name='detail'),
    path('<uuid:id>/toggle/', AutomationToggleView.as_view(), name='toggle'),
    path('<uuid:id>/test/', AutomationTestView.as_view(), name='test'),
    path('<uuid:id>/runs/', AutomationRunListView.as_view(), name='runs'),
    path('<uuid:automation_id>/conditions/', ConditionListCreateView.as_view(), name='conditions'),
    path('<uuid:automation_id>/actions/', ActionListCreateView.as_view(), name='actions'),

    # Scheduled QR behavior
    path('schedules/', QRScheduleListCreateView.as_view(), name='schedules-list'),
    path('schedules/<uuid:id>/', QRScheduleDetailView.as_view(), name='schedule-detail'),
    path('schedules/<uuid:id>/toggle/', QRScheduleToggleView.as_view(), name='schedule-toggle'),
    path('schedules/<uuid:id>/run/', QRScheduleRunNowView.as_view(), name='schedule-run'),

    # External hooks (n8n / Zapier / Make)
    path('hooks/', ExternalHookListCreateView.as_view(), name='hooks-list'),
    path('hooks/<uuid:id>/', ExternalHookDetailView.as_view(), name='hook-detail'),
    path('hooks/<uuid:id>/test/', ExternalHookTestView.as_view(), name='hook-test'),
]
