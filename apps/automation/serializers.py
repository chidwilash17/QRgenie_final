"""
Automation Engine — Serializers
=================================
"""
from rest_framework import serializers
from .models import (
    Automation, AutomationCondition, AutomationAction,
    AutomationRun, AutomationActionLog,
    QRSchedule, QRScheduleLog, ExternalHookSubscription,
)


class AutomationConditionSerializer(serializers.ModelSerializer):
    value = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    class Meta:
        model = AutomationCondition
        fields = ['id', 'field', 'operator', 'value', 'order']
        read_only_fields = ['id']


class AutomationActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationAction
        fields = ['id', 'action_type', 'order', 'config']
        read_only_fields = ['id']


class AutomationActionLogSerializer(serializers.ModelSerializer):
    action_type = serializers.CharField(source='action.action_type', read_only=True)

    class Meta:
        model = AutomationActionLog
        fields = [
            'id', 'action', 'action_type', 'status',
            'input_data', 'output_data', 'error_message',
            'executed_at', 'duration_ms',
        ]


class AutomationRunSerializer(serializers.ModelSerializer):
    action_logs = AutomationActionLogSerializer(many=True, read_only=True)

    class Meta:
        model = AutomationRun
        fields = [
            'id', 'status', 'trigger_data', 'started_at',
            'completed_at', 'duration_ms', 'error_message', 'action_logs',
        ]


class AutomationListSerializer(serializers.ModelSerializer):
    conditions_count = serializers.IntegerField(source='conditions.count', read_only=True)
    actions_count = serializers.IntegerField(source='actions.count', read_only=True)
    qr_code_title = serializers.CharField(source='qr_code.title', read_only=True, default=None)

    class Meta:
        model = Automation
        fields = [
            'id', 'name', 'description', 'trigger_type', 'status',
            'qr_code', 'qr_code_title', 'cron_expression',
            'total_runs', 'last_run_at', 'conditions_count', 'actions_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_runs', 'last_run_at', 'created_at', 'updated_at']


class AutomationDetailSerializer(serializers.ModelSerializer):
    conditions = AutomationConditionSerializer(many=True, read_only=True)
    actions = AutomationActionSerializer(many=True, read_only=True)
    recent_runs = serializers.SerializerMethodField()

    class Meta:
        model = Automation
        fields = [
            'id', 'name', 'description', 'trigger_type', 'status',
            'qr_code', 'cron_expression', 'total_runs', 'last_run_at',
            'conditions', 'actions', 'recent_runs',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_runs', 'last_run_at', 'created_at', 'updated_at']

    def get_recent_runs(self, obj):
        runs = obj.runs.all()[:5]
        return AutomationRunSerializer(runs, many=True).data


class AutomationCreateSerializer(serializers.ModelSerializer):
    conditions = AutomationConditionSerializer(many=True, required=False)
    actions = AutomationActionSerializer(many=True, required=False)

    class Meta:
        model = Automation
        fields = [
            'id', 'name', 'description', 'trigger_type', 'status',
            'qr_code', 'cron_expression', 'conditions', 'actions',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        conditions_data = validated_data.pop('conditions', [])
        actions_data = validated_data.pop('actions', [])
        request = self.context['request']

        automation = Automation.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )

        for i, cond in enumerate(conditions_data):
            cond.setdefault('order', i)
            AutomationCondition.objects.create(
                automation=automation, **cond
            )

        for i, act in enumerate(actions_data):
            act.setdefault('order', i)
            AutomationAction.objects.create(
                automation=automation, **act
            )

        return automation

    def update(self, instance, validated_data):
        conditions_data = validated_data.pop('conditions', None)
        actions_data = validated_data.pop('actions', None)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if conditions_data is not None:
            instance.conditions.all().delete()
            for i, cond in enumerate(conditions_data):
                cond.setdefault('order', i)
                AutomationCondition.objects.create(
                    automation=instance, **cond
                )

        if actions_data is not None:
            instance.actions.all().delete()
            for i, act in enumerate(actions_data):
                act.setdefault('order', i)
                AutomationAction.objects.create(
                    automation=instance, **act
                )

        return instance


# ─── QR Schedule Serializers ────────────────────────────────────────────────

class QRScheduleLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRScheduleLog
        fields = ['id', 'status', 'executed_at', 'details', 'error_message']


class QRScheduleSerializer(serializers.ModelSerializer):
    qr_code_title = serializers.CharField(source='qr_code.title', read_only=True, default=None)
    recent_logs = serializers.SerializerMethodField()

    class Meta:
        model = QRSchedule
        fields = [
            'id', 'name', 'qr_code', 'qr_code_title', 'action', 'is_active',
            'scheduled_at', 'repeat', 'cron_expression', 'tz', 'payload',
            'last_run_at', 'next_run_at', 'total_runs',
            'recent_logs', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_run_at', 'next_run_at', 'total_runs', 'created_at', 'updated_at']

    def get_recent_logs(self, obj):
        logs = obj.logs.all()[:5]
        return QRScheduleLogSerializer(logs, many=True).data


class QRScheduleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRSchedule
        fields = [
            'name', 'qr_code', 'action', 'is_active',
            'scheduled_at', 'repeat', 'cron_expression', 'tz', 'payload',
        ]

    def validate(self, data):
        if data.get('repeat') == 'cron' and not data.get('cron_expression'):
            raise serializers.ValidationError({'cron_expression': 'Required for cron repeat type.'})
        if data.get('repeat') == 'once' and not data.get('scheduled_at'):
            raise serializers.ValidationError({'scheduled_at': 'Required for one-time schedules.'})
        if data.get('action') in ('change_url', 'change_fallback') and not data.get('payload', {}).get('url'):
            raise serializers.ValidationError({'payload': 'URL required for change_url/change_fallback actions.'})
        return data

    def create(self, validated_data):
        request = self.context['request']
        schedule = QRSchedule.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )
        # Compute next_run_at
        from apps.automation.schedule_engine import compute_next_run
        schedule.next_run_at = compute_next_run(schedule)
        schedule.save(update_fields=['next_run_at'])
        return schedule


# ─── External Hook (n8n/Zapier) Serializers ─────────────────────────────────

class ExternalHookSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalHookSubscription
        fields = [
            'id', 'event', 'target_url', 'is_active', 'platform',
            'consecutive_failures', 'last_failure_at', 'created_at',
        ]
        read_only_fields = ['id', 'consecutive_failures', 'last_failure_at', 'created_at']


class ExternalHookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalHookSubscription
        fields = ['event', 'target_url', 'platform']

    def validate_event(self, value):
        valid = [c[0] for c in ExternalHookSubscription.EVENT_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(f'Invalid event: {value}. Valid: {valid}')
        return value

    def create(self, validated_data):
        request = self.context['request']
        return ExternalHookSubscription.objects.create(
            organization=request.user.organization,
            created_by=request.user,
            **validated_data,
        )
