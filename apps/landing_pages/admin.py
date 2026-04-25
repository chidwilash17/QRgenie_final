from django.contrib import admin
from .models import LandingPage, LandingPageTemplate


@admin.register(LandingPageTemplate)
class LandingPageTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'is_premium', 'created_at']
    list_filter = ['category', 'is_active', 'is_premium']


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'organization', 'is_published', 'is_ai_generated', 'view_count', 'created_at']
    list_filter = ['is_published', 'is_ai_generated']
    search_fields = ['title', 'slug']
    readonly_fields = ['id', 'view_count']
