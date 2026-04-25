"""Public URLs for landing page serving at /p/<slug>/"""
from django.urls import path
from .views import (
    LandingPagePublicView,
    PasswordVerifyView,
    FileDownloadView,
    PageEventView,
    NewsletterSubscribeView,
    SurveySubmitView,
)

urlpatterns = [
    # Main page serve
    path('<slug:slug>/', LandingPagePublicView.as_view(), name='public-page'),
    # Password verification — POST {password}
    path('<slug:slug>/verify/', PasswordVerifyView.as_view(), name='public-page-verify'),
    # File delivery download tracker — redirects to actual file
    path('<slug:slug>/download/', FileDownloadView.as_view(), name='public-page-download'),
    # Lightweight event tracker — POST {event, meta}
    path('<slug:slug>/event/', PageEventView.as_view(), name='public-page-event'),
    # Newsletter subscription — POST {email, name}
    path('<slug:slug>/subscribe/', NewsletterSubscribeView.as_view(), name='public-page-subscribe'),
    # Survey / Form submission — POST {ratings, answers}
    path('<slug:slug>/submit/', SurveySubmitView.as_view(), name='public-page-submit'),
]
