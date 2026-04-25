from django.contrib import admin
from .models import AIGenerationLog


@admin.register(AIGenerationLog)
class AIGenerationLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'generation_type', 'status', 'model_used', 'total_tokens', 'organization', 'created_at']
    list_filter = ['generation_type', 'status', 'model_used']
    search_fields = ['prompt']
    readonly_fields = ['id', 'result', 'raw_response']
    date_hierarchy = 'created_at'
