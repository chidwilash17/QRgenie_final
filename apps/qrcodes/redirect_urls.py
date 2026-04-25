from django.urls import path
from .redirect_views import RedirectView, ResolveLocationView

urlpatterns = [
    path('', RedirectView.as_view(), name='redirect'),
    path('resolve-location/', ResolveLocationView.as_view(), name='resolve-location'),
]
