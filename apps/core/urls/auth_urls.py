from django.urls import path
from apps.core.views import LoginView, RegisterView, LogoutView, RefreshTokenView, MeView, ChangePasswordView, ClerkTokenExchangeView

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('refresh/', RefreshTokenView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('clerk-exchange/', ClerkTokenExchangeView.as_view(), name='auth-clerk-exchange'),
]
