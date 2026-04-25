from django.urls import path
from .pdf_views import PDFViewerPageView, PDFRawFileView

urlpatterns = [
    path('', PDFViewerPageView.as_view(), name='pdf-viewer'),
    path('raw/', PDFRawFileView.as_view(), name='pdf-raw'),
]
