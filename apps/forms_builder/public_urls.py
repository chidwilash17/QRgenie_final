from django.urls import path
from .views import PublicFormView, PublicFormSubmitView

urlpatterns = [
    path('<str:slug>/', PublicFormView.as_view(), name='public-form'),
    path('<str:slug>/submit/', PublicFormSubmitView.as_view(), name='public-form-submit'),
]
