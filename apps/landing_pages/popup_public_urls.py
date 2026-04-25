"""
Popup Builder — Public embed URLs (Feature 14)
"""
from django.urls import path
from .views import PopupEmbedView, PopupClickTrackView, PopupSubmitView

app_name = 'popup_public'

urlpatterns = [
    path('embed.js', PopupEmbedView.as_view(), name='embed'),
    path('click/', PopupClickTrackView.as_view(), name='click'),
    path('submit/', PopupSubmitView.as_view(), name='submit'),
]
