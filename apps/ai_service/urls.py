from django.urls import path
from .views import (
    AIGenerateLandingPageView,
    AIAnalyticsSummaryView,
    AISmartRouteView,
    AIABOptimizeView,
    AIGenerationLogListView,
    AITokenUsageView,
    GeneratePageView,
    AIPlanPageView,
    AIPromptPageView,
    LinkFormToPageView,
    AIChatAssistantView,
)

app_name = 'ai_service'

urlpatterns = [
    path('generate-landing-page/', AIGenerateLandingPageView.as_view(), name='generate-landing-page'),
    path('generate-page/', GeneratePageView.as_view(), name='generate-page'),
    path('analytics-summary/', AIAnalyticsSummaryView.as_view(), name='analytics-summary'),
    path('smart-route/', AISmartRouteView.as_view(), name='smart-route'),
    path('ab-optimize/', AIABOptimizeView.as_view(), name='ab-optimize'),
    path('logs/', AIGenerationLogListView.as_view(), name='logs'),
    path('usage/', AITokenUsageView.as_view(), name='usage'),
    path('plan-page/', AIPlanPageView.as_view(), name='plan-page'),
    path('prompt-page/', AIPromptPageView.as_view(), name='prompt-page'),
    path('link-form-to-page/', LinkFormToPageView.as_view(), name='link-form-to-page'),
    path('chat/', AIChatAssistantView.as_view(), name='chat'),
]
