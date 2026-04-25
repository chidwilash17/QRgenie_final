"""
Forms Builder — Serializers
"""
from rest_framework import serializers
from .models import (
    Form, FormField, FormFieldLocationRestriction,
    FormSubmission, SubmissionAnswer,
)


class LocationRestrictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormFieldLocationRestriction
        fields = ['city', 'state', 'country', 'restriction_message']


class FormFieldSerializer(serializers.ModelSerializer):
    location_restriction = LocationRestrictionSerializer(required=False, allow_null=True)

    class Meta:
        model = FormField
        fields = [
            'id', 'order', 'field_type', 'label', 'placeholder', 'help_text',
            'is_required', 'options',
            'min_length', 'max_length', 'min_value', 'max_value',
            'scale_min', 'scale_max', 'scale_min_label', 'scale_max_label',
            'max_file_size_mb', 'allowed_file_types',
            'is_location_restricted', 'location_restriction',
        ]

    def create(self, validated_data):
        loc_data = validated_data.pop('location_restriction', None)
        field = FormField.objects.create(**validated_data)
        if loc_data:
            FormFieldLocationRestriction.objects.create(field=field, **loc_data)
        return field

    def update(self, instance, validated_data):
        loc_data = validated_data.pop('location_restriction', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if loc_data is not None:
            FormFieldLocationRestriction.objects.update_or_create(
                field=instance, defaults=loc_data
            )
        elif hasattr(instance, 'location_restriction'):
            instance.location_restriction.delete()
        return instance


class FormSerializer(serializers.ModelSerializer):
    fields = FormFieldSerializer(many=True, required=False)
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    total_submissions = serializers.IntegerField(read_only=True)
    public_url = serializers.CharField(read_only=True)

    class Meta:
        model = Form
        fields = [
            'id', 'slug', 'title', 'description',
            'background_theme', 'header_color',
            'is_active', 'accept_responses', 'requires_auth',
            'requires_respondent_info', 'limit_one_response_per_respondent',
            'allow_multiple_responses', 'max_responses', 'close_date',
            'confirmation_message', 'confirmation_redirect_url',
            'qr_slug', 'owner_name', 'total_submissions', 'public_url',
            'fields', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'owner_name', 'total_submissions', 'public_url']

    def create(self, validated_data):
        fields_data = validated_data.pop('fields', [])
        form = Form.objects.create(**validated_data)
        for i, fd in enumerate(fields_data):
            fd['order'] = fd.get('order', i)
            fd['form'] = form
            loc = fd.pop('location_restriction', None)
            field = FormField.objects.create(**fd)
            if loc:
                FormFieldLocationRestriction.objects.create(field=field, **loc)
        return form

    def update(self, instance, validated_data):
        fields_data = validated_data.pop('fields', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if fields_data is not None:
            # Replace all fields
            instance.fields.all().delete()
            for i, fd in enumerate(fields_data):
                fd['order'] = fd.get('order', i)
                fd['form'] = instance
                loc = fd.pop('location_restriction', None)
                field = FormField.objects.create(**fd)
                if loc:
                    FormFieldLocationRestriction.objects.create(field=field, **loc)
        return instance


class FormListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    total_submissions = serializers.IntegerField(read_only=True)
    public_url = serializers.CharField(read_only=True)

    class Meta:
        model = Form
        fields = [
            'id', 'slug', 'title', 'description',
            'background_theme', 'header_color',
            'is_active', 'accept_responses',
            'requires_respondent_info', 'limit_one_response_per_respondent',
            'total_submissions', 'public_url',
            'created_at', 'updated_at',
        ]


# ── Submission serializers ──────────────────────────────────────

class SubmissionAnswerSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionAnswer
        fields = [
            'id', 'field', 'field_label', 'field_type',
            'text_value', 'number_value', 'json_value', 'file_url',
        ]

    def get_file_url(self, obj):
        if obj.file_value:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file_value.url)
            return obj.file_value.url
        return None


class FormSubmissionSerializer(serializers.ModelSerializer):
    answers = SubmissionAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = FormSubmission
        fields = [
            'id', 'submitted_at',
            'ip_address', 'city', 'state', 'country',
            'latitude', 'longitude',
            'respondent_name', 'respondent_email',
            'answers',
        ]


class FormSubmissionCreateSerializer(serializers.Serializer):
    """Used for POST /f/<slug>/submit/"""
    answers = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)


# ── Public form serializer (strips owner info, adds location check) ──

class PublicFormFieldSerializer(serializers.ModelSerializer):
    location_restriction = LocationRestrictionSerializer(read_only=True)

    class Meta:
        model = FormField
        fields = [
            'id', 'order', 'field_type', 'label', 'placeholder', 'help_text',
            'is_required', 'options',
            'min_length', 'max_length', 'min_value', 'max_value',
            'scale_min', 'scale_max', 'scale_min_label', 'scale_max_label',
            'max_file_size_mb', 'allowed_file_types',
            'is_location_restricted', 'location_restriction',
        ]


class PublicFormSerializer(serializers.ModelSerializer):
    fields = PublicFormFieldSerializer(many=True, read_only=True)

    class Meta:
        model = Form
        fields = [
            'id', 'slug', 'title', 'description',
            'background_theme', 'header_color',
            'is_active', 'requires_auth', 'accept_responses',
            'requires_respondent_info', 'limit_one_response_per_respondent',
            'confirmation_message', 'confirmation_redirect_url',
            'fields',
        ]
