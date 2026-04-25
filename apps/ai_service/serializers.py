from rest_framework import serializers
from .models import AIGenerationLog


class AIGenerationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIGenerationLog
        fields = [
            'id', 'generation_type', 'status', 'prompt', 'model_used',
            'result', 'prompt_tokens', 'completion_tokens', 'total_tokens',
            'qr_code', 'error_message', 'created_at', 'completed_at',
        ]
        read_only_fields = ['id', 'status', 'result', 'prompt_tokens', 'completion_tokens',
                            'total_tokens', 'error_message', 'created_at', 'completed_at']


class GenerateLandingPageRequestSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField(required=False)
    business_name = serializers.CharField(max_length=200)
    business_type = serializers.CharField(max_length=100, default='general')
    description = serializers.CharField(max_length=2000)
    links = serializers.ListField(child=serializers.DictField(), required=False, default=[])
    style = serializers.ChoiceField(choices=['modern', 'minimal', 'bold', 'classic', 'playful'], default='modern')
    color_scheme = serializers.CharField(max_length=20, default='#6366f1')


class AnalyticsSummaryRequestSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField()


class SmartRouteRequestSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField()


class ABOptimizeRequestSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField()
    variants = serializers.ListField(child=serializers.DictField())
