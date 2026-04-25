from django.urls import path
from .views import (
    LandingPageListCreateView,
    LandingPageDetailView,
    LandingPagePublishToggleView,
    LandingPageDuplicateView,
    TemplateListView,
    MediaUploadView,
)

app_name = 'landing_pages'

urlpatterns = [
    path('', LandingPageListCreateView.as_view(), name='list-create'),
    path('templates/', TemplateListView.as_view(), name='templates'),
    path('media/upload/', MediaUploadView.as_view(), name='media-upload'),
    path('<uuid:id>/', LandingPageDetailView.as_view(), name='detail'),
    path('<uuid:id>/publish/', LandingPagePublishToggleView.as_view(), name='publish-toggle'),
    path('<uuid:id>/duplicate/', LandingPageDuplicateView.as_view(), name='duplicate'),
]
