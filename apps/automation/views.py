"""
Automation Engine — Views
===========================
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.permissions import IsOrgMember, IsOrgOwnerOrAdmin
from .models import (
    Automation, AutomationRun, AutomationAction, AutomationCondition,
    QRSchedule, ExternalHookSubscription,
)
from .serializers import (
    AutomationListSerializer, AutomationDetailSerializer,
    AutomationCreateSerializer, AutomationRunSerializer,
    AutomationConditionSerializer, AutomationActionSerializer,
    QRScheduleSerializer, QRScheduleCreateSerializer,
    ExternalHookSubscriptionSerializer, ExternalHookCreateSerializer,
)


class AutomationListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/automation/
    POST /api/v1/automation/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AutomationCreateSerializer
        return AutomationListSerializer

    def get_queryset(self):
        qs = Automation.objects.filter(organization=self.request.user.organization)
        status_filter = self.request.query_params.get('status')
        trigger = self.request.query_params.get('trigger_type')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if trigger:
            qs = qs.filter(trigger_type=trigger)
        return qs

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Check org automation limit
        org = self.request.user.organization
        current = Automation.objects.filter(organization=org).count()
        if current >= org.max_automations:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(f'Automation limit reached ({org.max_automations}). Upgrade plan.')
        serializer.save()


class AutomationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/automation/<id>/
    PUT    /api/v1/automation/<id>/
    DELETE /api/v1/automation/<id>/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return AutomationCreateSerializer
        return AutomationDetailSerializer

    def get_queryset(self):
        return Automation.objects.filter(organization=self.request.user.organization)


class AutomationToggleView(APIView):
    """
    POST /api/v1/automation/<id>/toggle/
    Toggle automation between active and paused.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            auto = Automation.objects.get(id=id, organization=request.user.organization)
        except Automation.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if auto.status == 'active':
            auto.status = 'paused'
        else:
            auto.status = 'active'
        auto.save(update_fields=['status', 'updated_at'])

        return Response({'id': str(auto.id), 'status': auto.status})


class AutomationTestView(APIView):
    """
    POST /api/v1/automation/<id>/test/
    Test-fire an automation with mock context.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, id):
        try:
            auto = Automation.objects.get(id=id, organization=request.user.organization)
        except Automation.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Build smart mock context that satisfies the automation's conditions
        base_context = {
            'qr_id': str(auto.qr_code_id) if auto.qr_code_id else 'test-qr-id',
            'country': 'US',
            'city': 'Test City',
            'device_type': 'mobile',
            'os': 'Android',
            'browser': 'Chrome',
            'ip_address': '127.0.0.1',
            'scan_count': 1,
        }
        # Override base values with condition expectations so test passes conditions
        for cond in auto.conditions.all():
            if cond.operator in ('eq', 'contains', 'in'):
                val = cond.value.split(',')[0].strip() if cond.operator == 'in' else cond.value
                base_context[cond.field] = val
            elif cond.operator == 'gt':
                try:
                    base_context[cond.field] = float(cond.value) + 1
                except ValueError:
                    pass
            elif cond.operator == 'gte':
                try:
                    base_context[cond.field] = float(cond.value)
                except ValueError:
                    pass
            elif cond.operator == 'lt':
                try:
                    base_context[cond.field] = float(cond.value) - 1
                except ValueError:
                    pass
            elif cond.operator == 'lte':
                try:
                    base_context[cond.field] = float(cond.value)
                except ValueError:
                    pass

        # Allow user to override context via request body
        mock_context = request.data.get('context', base_context)

        from .tasks import _execute_automation_core
        try:
            _execute_automation_core(str(auto.id), mock_context)
        except Exception as e:
            return Response({
                'detail': f'Test completed with issues: {e}',
                'context': mock_context,
            })

        # Fetch the latest run to show actual results
        from .models import AutomationRun
        latest_run = AutomationRun.objects.filter(automation=auto).order_by('-started_at').first()
        run_info = {}
        if latest_run:
            run_info = {
                'run_status': latest_run.status,
                'error': latest_run.error_message or None,
                'action_results': [
                    {
                        'action': log.action.action_type,
                        'status': log.status,
                        'error': log.error_message or None,
                        'output': log.output_data,
                    }
                    for log in latest_run.action_logs.select_related('action').all()
                ],
            }

        msg = 'Test automation fired.'
        if run_info.get('run_status') == 'failed':
            msg = f"Test ran but failed: {run_info.get('error', 'Check action results')}"
        elif run_info.get('run_status') == 'partial':
            msg = 'Test ran but some actions failed. Check details.'
        elif run_info.get('run_status') == 'skipped':
            msg = 'Conditions not met — automation was skipped.'
        elif run_info.get('run_status') == 'success':
            msg = 'Test completed successfully! All actions executed.'

        return Response({'message': msg, 'context': mock_context, 'run': run_info})


class AutomationRunListView(generics.ListAPIView):
    """
    GET /api/v1/automation/<id>/runs/
    List execution history for an automation.
    """
    serializer_class = AutomationRunSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return AutomationRun.objects.filter(
            automation__id=self.kwargs['id'],
            automation__organization=self.request.user.organization,
        ).prefetch_related('action_logs')


class ConditionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/automation/<automation_id>/conditions/
    POST /api/v1/automation/<automation_id>/conditions/
    """
    serializer_class = AutomationConditionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return AutomationCondition.objects.filter(
            automation__id=self.kwargs['automation_id'],
            automation__organization=self.request.user.organization,
        )

    def perform_create(self, serializer):
        auto = Automation.objects.get(
            id=self.kwargs['automation_id'],
            organization=self.request.user.organization,
        )
        serializer.save(automation=auto)


class ActionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/automation/<automation_id>/actions/
    POST /api/v1/automation/<automation_id>/actions/
    """
    serializer_class = AutomationActionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return AutomationAction.objects.filter(
            automation__id=self.kwargs['automation_id'],
            automation__organization=self.request.user.organization,
        )

    def perform_create(self, serializer):
        auto = Automation.objects.get(
            id=self.kwargs['automation_id'],
            organization=self.request.user.organization,
        )
        serializer.save(automation=auto)


# ═══════════════════════════════════════════════════════════════════════════════
# QR Schedule Views — Scheduled QR behavior changes
# ═══════════════════════════════════════════════════════════════════════════════

class QRScheduleListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/automation/schedules/
    POST /api/v1/automation/schedules/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QRScheduleCreateSerializer
        return QRScheduleSerializer

    def get_queryset(self):
        qs = QRSchedule.objects.filter(organization=self.request.user.organization)
        qr_id = self.request.query_params.get('qr_code')
        if qr_id:
            qs = qs.filter(qr_code_id=qr_id)
        return qs.select_related('qr_code')


class QRScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/v1/automation/schedules/<id>/
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return QRScheduleCreateSerializer
        return QRScheduleSerializer

    def get_queryset(self):
        return QRSchedule.objects.filter(organization=self.request.user.organization)


class QRScheduleToggleView(APIView):
    """POST /api/v1/automation/schedules/<id>/toggle/"""
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request, id):
        try:
            sched = QRSchedule.objects.get(id=id, organization=request.user.organization)
        except QRSchedule.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        sched.is_active = not sched.is_active
        sched.save(update_fields=['is_active', 'updated_at'])
        return Response({'id': str(sched.id), 'is_active': sched.is_active})


class QRScheduleRunNowView(APIView):
    """POST /api/v1/automation/schedules/<id>/run/ — Execute schedule immediately."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, id):
        try:
            sched = QRSchedule.objects.get(id=id, organization=request.user.organization)
        except QRSchedule.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        from .schedule_engine import execute_schedule
        success, msg = execute_schedule(sched)
        return Response({'success': success, 'message': msg})


# ═══════════════════════════════════════════════════════════════════════════════
# External Hook (n8n / Zapier) Views — REST Hooks pattern
# ═══════════════════════════════════════════════════════════════════════════════

class ExternalHookListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/automation/hooks/
    POST /api/v1/automation/hooks/     (Zapier/n8n subscribe)
    """
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ExternalHookCreateSerializer
        return ExternalHookSubscriptionSerializer

    def get_queryset(self):
        return ExternalHookSubscription.objects.filter(
            organization=self.request.user.organization
        )


class ExternalHookDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /api/v1/automation/hooks/<id>/
    DELETE /api/v1/automation/hooks/<id>/   (Zapier/n8n unsubscribe)
    """
    serializer_class = ExternalHookSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    lookup_field = 'id'

    def get_queryset(self):
        return ExternalHookSubscription.objects.filter(
            organization=self.request.user.organization
        )


class ExternalHookTestView(APIView):
    """POST /api/v1/automation/hooks/<id>/test/ — Send test payload."""
    permission_classes = [permissions.IsAuthenticated, IsOrgOwnerOrAdmin]

    def post(self, request, id):
        try:
            hook = ExternalHookSubscription.objects.get(
                id=id, organization=request.user.organization
            )
        except ExternalHookSubscription.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from .schedule_engine import fire_external_hooks
        fire_external_hooks(
            event_type=hook.event,
            payload={'event': hook.event, 'test': True, 'message': 'Test hook from QRGenie'},
            org_id=str(hook.organization_id),
        )
        return Response({'detail': 'Test hook dispatched.'})
