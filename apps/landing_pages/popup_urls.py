"""
Popup Builder — API URLs (Feature 14)
"""
from django.urls import path
from .views import (
    PopupListCreateView,
    PopupDetailView,
    PopupPublishToggleView,
    PopupDuplicateView,
    PopupSubmissionListView,
)

app_name = 'popups'

urlpatterns = [
    path('', PopupListCreateView.as_view(), name='list-create'),
    path('<uuid:id>/', PopupDetailView.as_view(), name='detail'),
    path('<uuid:id>/publish/', PopupPublishToggleView.as_view(), name='publish-toggle'),
    path('<uuid:id>/duplicate/', PopupDuplicateView.as_view(), name='duplicate'),
    path('<uuid:id>/submissions/', PopupSubmissionListView.as_view(), name='submissions'),
]
