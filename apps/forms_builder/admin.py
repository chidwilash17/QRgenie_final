from django.contrib import admin
from .models import Form, FormField, FormFieldLocationRestriction, FormSubmission, SubmissionAnswer


class FormFieldInline(admin.TabularInline):
    model = FormField
    extra = 0
    fields = ['order', 'field_type', 'label', 'is_required', 'is_location_restricted']
    ordering = ['order']


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ['title', 'owner', 'slug', 'is_active', 'accept_responses', 'total_submissions', 'created_at']
    list_filter = ['is_active', 'accept_responses', 'background_theme']
    search_fields = ['title', 'slug', 'owner__email']
    inlines = [FormFieldInline]
    readonly_fields = ['slug', 'created_at', 'updated_at']


@admin.register(FormFieldLocationRestriction)
class LocationRestrictionAdmin(admin.ModelAdmin):
    list_display = ['field', 'city', 'state', 'country']
    search_fields = ['field__label', 'city', 'state', 'country']


class SubmissionAnswerInline(admin.TabularInline):
    model = SubmissionAnswer
    extra = 0
    readonly_fields = ['field_label', 'field_type', 'text_value', 'number_value', 'json_value', 'file_value']
    can_delete = False


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'form', 'submitted_at', 'ip_address', 'city', 'country']
    list_filter = ['form', 'country']
    search_fields = ['ip_address', 'city', 'country']
    inlines = [SubmissionAnswerInline]
    readonly_fields = ['submitted_at']
