from django.contrib import admin
from .models import Automation, AutomationCondition, AutomationAction, AutomationRun, AutomationActionLog


class ConditionInline(admin.TabularInline):
    model = AutomationCondition
    extra = 0


class ActionInline(admin.TabularInline):
    model = AutomationAction
    extra = 0


@admin.register(Automation)
class AutomationAdmin(admin.ModelAdmin):
    list_display = ['name', 'trigger_type', 'status', 'organization', 'total_runs', 'last_run_at', 'created_at']
    list_filter = ['status', 'trigger_type']
    search_fields = ['name', 'description']
    inlines = [ConditionInline, ActionInline]


class ActionLogInline(admin.TabularInline):
    model = AutomationActionLog
    extra = 0
    readonly_fields = ['action', 'status', 'input_data', 'output_data', 'error_message', 'executed_at']


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'automation', 'status', 'started_at', 'duration_ms']
    list_filter = ['status']
    inlines = [ActionLogInline]
