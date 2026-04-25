from django.urls import path
from .views import (
    FormListCreateView,
    FormDetailView,
    FormFieldsView,
    FormFieldDetailView,
    FormFieldsReorderView,
    SubmissionListView,
    SubmissionDetailView,
    SubmissionDeleteView,
    SubmissionStatsView,
    FormGenerateQRView,
)

app_name = 'forms_builder'

urlpatterns = [
    path('', FormListCreateView.as_view(), name='form-list-create'),
    path('<uuid:pk>/', FormDetailView.as_view(), name='form-detail'),
    path('<uuid:pk>/fields/', FormFieldsView.as_view(), name='form-fields'),
    path('<uuid:pk>/fields/reorder/', FormFieldsReorderView.as_view(), name='form-fields-reorder'),
    path('<uuid:form_pk>/fields/<uuid:field_pk>/', FormFieldDetailView.as_view(), name='form-field-detail'),
    path('<uuid:pk>/submissions/', SubmissionListView.as_view(), name='form-submissions'),
    path('<uuid:pk>/stats/', SubmissionStatsView.as_view(), name='form-stats'),
    path('<uuid:form_pk>/submissions/<uuid:sub_pk>/', SubmissionDetailView.as_view(), name='submission-detail'),
    path('<uuid:form_pk>/submissions/<uuid:sub_pk>/delete/', SubmissionDeleteView.as_view(), name='submission-delete'),
    path('<uuid:pk>/generate-qr/', FormGenerateQRView.as_view(), name='form-generate-qr'),
]
