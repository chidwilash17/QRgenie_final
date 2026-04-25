from django.urls import path
from .video_views import VideoPlayerPageView, VideoRawFileView

urlpatterns = [
    path('', VideoPlayerPageView.as_view(), name='video-player'),
    path('raw/', VideoRawFileView.as_view(), name='video-raw'),
]
