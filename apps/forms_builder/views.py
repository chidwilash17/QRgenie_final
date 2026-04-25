"""
Forms Builder — Views
======================
Admin API (auth required) + Public submission API (no auth).
"""
import logging
import json
from django.utils import timezone
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import (
    Form, FormField, FormFieldLocationRestriction,
    FormSubmission, SubmissionAnswer,
)
from .serializers import (
    FormSerializer, FormListSerializer, FormFieldSerializer,
    PublicFormSerializer, FormSubmissionSerializer,
    FormSubmissionCreateSerializer,
)

logger = logging.getLogger('apps.forms_builder')


def _get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _resolve_ip_location(ip: str):
    """Returns (city, state, country) for a public IP via ipinfo.io."""
    if not ip or any(ip.startswith(p) for p in ('127.', '10.', '192.168.', '::1')):
        return '', '', ''
    try:
        import json as _j
        from urllib.request import urlopen, Request
        req = Request(
            f"https://ipinfo.io/{ip}/json",
            headers={'User-Agent': 'QRGenie/1.0', 'Accept': 'application/json'},
        )
        with urlopen(req, timeout=4) as resp:
            data = _j.loads(resp.read().decode())
        city = data.get('city', '')
        state = data.get('region', '')
        country = data.get('country', '')
        return city, state, country
    except Exception as e:
        logger.warning(f"[Forms] GeoIP failed for {ip}: {e}")
        return '', '', ''


# ──────────────────────────────────────────────────────────────────────────────
# Admin: CRUD Forms
# ──────────────────────────────────────────────────────────────────────────────

class FormListCreateView(APIView):
    """
    GET  /api/v1/forms/           — list current user's forms
    POST /api/v1/forms/           — create a new form
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        forms = Form.objects.filter(owner=request.user).order_by('-created_at')
        serializer = FormListSerializer(forms, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FormSerializer(data=request.data)
        if serializer.is_valid():
            form = serializer.save(owner=request.user)
            return Response(FormSerializer(form).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FormDetailView(APIView):
    """
    GET    /api/v1/forms/<id>/   — fetch form with fields
    PUT    /api/v1/forms/<id>/   — full update (replaces all fields)
    PATCH  /api/v1/forms/<id>/   — partial update (form metadata only)
    DELETE /api/v1/forms/<id>/   — delete form
    """
    permission_classes = [IsAuthenticated]

    def _get_form(self, pk, user):
        try:
            return Form.objects.get(id=pk, owner=user)
        except Form.DoesNotExist:
            return None

    def get(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(FormSerializer(form).data)

    def put(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = FormSerializer(form, data=request.data)
        if serializer.is_valid():
            form = serializer.save()
            return Response(FormSerializer(form).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = FormSerializer(form, data=request.data, partial=True)
        if serializer.is_valid():
            form = serializer.save()
            return Response(FormSerializer(form).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        form.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FormFieldsView(APIView):
    """
    GET  /api/v1/forms/<id>/fields/        — list fields
    POST /api/v1/forms/<id>/fields/        — add a new field
    PUT  /api/v1/forms/<id>/fields/reorder/ — reorder fields [{id, order}]
    """
    permission_classes = [IsAuthenticated]

    def _get_form(self, pk, user):
        try:
            return Form.objects.get(id=pk, owner=user)
        except Form.DoesNotExist:
            return None

    def get(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=404)
        return Response(FormFieldSerializer(form.fields.all(), many=True).data)

    def post(self, request, pk):
        form = self._get_form(pk, request.user)
        if not form:
            return Response({'error': 'Not found.'}, status=404)
        serializer = FormFieldSerializer(data=request.data)
        if serializer.is_valid():
            field = serializer.save(form=form)
            return Response(FormFieldSerializer(field).data, status=201)
        return Response(serializer.errors, status=400)


class FormFieldDetailView(APIView):
    """
    PATCH  /api/v1/forms/<form_id>/fields/<field_id>/
    DELETE /api/v1/forms/<form_id>/fields/<field_id>/
    """
    permission_classes = [IsAuthenticated]

    def _get_field(self, form_pk, field_pk, user):
        try:
            form = Form.objects.get(id=form_pk, owner=user)
            return FormField.objects.get(id=field_pk, form=form)
        except (Form.DoesNotExist, FormField.DoesNotExist):
            return None

    def patch(self, request, form_pk, field_pk):
        field = self._get_field(form_pk, field_pk, request.user)
        if not field:
            return Response({'error': 'Not found.'}, status=404)
        serializer = FormFieldSerializer(field, data=request.data, partial=True)
        if serializer.is_valid():
            field = serializer.save()
            return Response(FormFieldSerializer(field).data)
        return Response(serializer.errors, status=400)

    def delete(self, request, form_pk, field_pk):
        field = self._get_field(form_pk, field_pk, request.user)
        if not field:
            return Response({'error': 'Not found.'}, status=404)
        field.delete()
        return Response(status=204)


class FormFieldsReorderView(APIView):
    """PUT /api/v1/forms/<id>/fields/reorder/  Body: [{id, order}, ...]"""
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        try:
            form = Form.objects.get(id=pk, owner=request.user)
        except Form.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        order_data = request.data if isinstance(request.data, list) else []
        for item in order_data:
            FormField.objects.filter(id=item['id'], form=form).update(order=item['order'])
        return Response({'ok': True})


# ──────────────────────────────────────────────────────────────────────────────
# Admin: Submissions
# ──────────────────────────────────────────────────────────────────────────────

class SubmissionListView(APIView):
    """
    GET /api/v1/forms/<id>/submissions/?page=1&country=IN&city=Bangalore

    Returns a paginated response:
      count    — total matching submissions
      page     — current page number
      page_size — items per page
      results  — list of FormSubmission objects (serialized)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            form = Form.objects.get(id=pk, owner=request.user)
        except Form.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        qs = form.submissions.prefetch_related('answers__field').order_by('-submitted_at')

        # Filters
        country = request.query_params.get('country')
        city = request.query_params.get('city')
        if country:
            qs = qs.filter(country__iexact=country)
        if city:
            qs = qs.filter(city__icontains=city)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        total = qs.count()
        start = (page - 1) * page_size
        submissions = qs[start:start + page_size]

        serializer = FormSubmissionSerializer(submissions, many=True, context={'request': request})
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class SubmissionDetailView(APIView):
    """GET /api/v1/forms/<form_id>/submissions/<sub_id>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, form_pk, sub_pk):
        try:
            form = Form.objects.get(id=form_pk, owner=request.user)
            sub = form.submissions.prefetch_related('answers').get(id=sub_pk)
        except (Form.DoesNotExist, FormSubmission.DoesNotExist):
            return Response({'error': 'Not found.'}, status=404)
        return Response(FormSubmissionSerializer(sub, context={'request': request}).data)


class SubmissionDeleteView(APIView):
    """DELETE /api/v1/forms/<form_id>/submissions/<sub_id>/"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, form_pk, sub_pk):
        try:
            form = Form.objects.get(id=form_pk, owner=request.user)
            sub = form.submissions.get(id=sub_pk)
        except (Form.DoesNotExist, FormSubmission.DoesNotExist):
            return Response({'error': 'Not found.'}, status=404)
        sub.delete()
        return Response(status=204)


class SubmissionStatsView(APIView):
    """GET /api/v1/forms/<id>/stats/ — aggregate stats for dashboard"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            form = Form.objects.get(id=pk, owner=request.user)
        except Form.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        from django.db.models import Count
        from datetime import date, timedelta

        subs = form.submissions
        total = subs.count()
        today_count = subs.filter(submitted_at__date=date.today()).count()
        week_count = subs.filter(submitted_at__date__gte=date.today() - timedelta(days=7)).count()

        country_breakdown = list(
            subs.exclude(country='').values('country')
            .annotate(count=Count('id')).order_by('-count')[:10]
        )
        city_breakdown = list(
            subs.exclude(city='').values('city', 'country')
            .annotate(count=Count('id')).order_by('-count')[:10]
        )
        daily_trend = list(
            subs.filter(submitted_at__date__gte=date.today() - timedelta(days=30))
            .extra(select={'day': 'DATE(submitted_at)'})
            .values('day').annotate(count=Count('id')).order_by('day')
        )

        # Field-level answer distributions for choice fields
        field_stats = []
        for field in form.fields.filter(field_type__in=['radio', 'dropdown', 'checkbox', 'rating', 'scale']):
            answers = list(
                SubmissionAnswer.objects.filter(field=field)
                .values_list('text_value', 'json_value')
            )
            counts: dict = {}
            for tv, jv in answers:
                if jv:
                    for v in (jv if isinstance(jv, list) else [jv]):
                        counts[str(v)] = counts.get(str(v), 0) + 1
                elif tv:
                    counts[tv] = counts.get(tv, 0) + 1
            field_stats.append({
                'field_id': str(field.id),
                'label': field.label,
                'type': field.field_type,
                'counts': counts,
            })

        return Response({
            'total': total,
            'today': today_count,
            'this_week': week_count,
            'country_breakdown': country_breakdown,
            'city_breakdown': city_breakdown,
            'daily_trend': daily_trend,
            'field_stats': field_stats,
        })


# ──────────────────────────────────────────────────────────────────────────────
# Public: Form Fill
# ──────────────────────────────────────────────────────────────────────────────

class PublicFormView(APIView):
    """
    GET /api/v1/public/forms/<slug>/
    Returns the form definition for public filling.
    Optionally includes location-check results for the caller's IP.
    """
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            form = Form.objects.prefetch_related(
                'fields', 'fields__location_restriction'
            ).get(slug=slug, is_active=True)
        except Form.DoesNotExist:
            return Response({'error': 'Form not found.'}, status=404)

        if not form.accept_responses:
            return Response({'error': 'This form is no longer accepting responses.'}, status=403)

        if form.close_date and timezone.now() > form.close_date:
            return Response({'error': 'This form has closed.'}, status=403)

        data = PublicFormSerializer(form).data

        # Annotate each field with whether the caller's IP passes location check
        ip = _get_client_ip(request)
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        caller_city, caller_state, caller_country = _resolve_ip_location(ip)

        for field_data in data['fields']:
            field_data['location_allowed'] = True  # default
            if field_data.get('is_location_restricted') and field_data.get('location_restriction'):
                lr = field_data['location_restriction']
                field_data['location_allowed'] = _check_location(
                    lr, caller_city, caller_state, caller_country,
                )

        data['caller_location'] = {
            'city': caller_city,
            'state': caller_state,
            'country': caller_country,
        }
        return Response(data)


def _check_location(lr_data: dict, city: str, state: str, country: str) -> bool:
    city_ok = (not lr_data.get('city')) or (
        lr_data['city'].lower() in (city or '').lower()
    )
    state_ok = (not lr_data.get('state')) or (
        lr_data['state'].lower() in (state or '').lower()
    )
    country_ok = (not lr_data.get('country')) or (
        lr_data['country'].upper() == (country or '').upper()
    )
    return city_ok and state_ok and country_ok


class PublicFormSubmitView(APIView):
    """
    POST /api/v1/public/forms/<slug>/submit/
    Accepts multipart/form-data OR JSON.
    Body: { answers: [{field_id, value, file?}, ...], lat?, lng? }
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, slug):
        try:
            form = Form.objects.prefetch_related(
                'fields', 'fields__location_restriction'
            ).get(slug=slug, is_active=True)
        except Form.DoesNotExist:
            return Response({'error': 'Form not found.'}, status=404)

        if not form.accept_responses:
            return Response({'error': 'This form is no longer accepting responses.'}, status=403)

        if form.close_date and timezone.now() > form.close_date:
            return Response({'error': 'Form has closed.'}, status=403)

        if form.max_responses and form.submissions.count() >= form.max_responses:
            return Response({'error': 'Maximum responses reached.'}, status=403)

        # ── Respondent identity ──
        respondent_name = (request.data.get('respondent_name') or '').strip()
        respondent_email = (request.data.get('respondent_email') or '').strip().lower()

        if form.requires_respondent_info:
            if not respondent_name:
                return Response({'error': 'Please enter your name.'}, status=400)
            if not respondent_email or '@' not in respondent_email:
                return Response({'error': 'Please enter a valid email address.'}, status=400)

        if form.limit_one_response_per_respondent and respondent_email:
            already = form.submissions.filter(respondent_email=respondent_email).exists()
            if already:
                return Response(
                    {'error': 'You have already submitted this form.'},
                    status=403,
                )

        # ── Parse answers ──
        # Support both multipart (answers as JSON string field) and JSON body
        ip = _get_client_ip(request)
        caller_city, caller_state, caller_country = _resolve_ip_location(ip)

        raw_answers = request.data.get('answers', [])
        if isinstance(raw_answers, str):
            try:
                raw_answers = json.loads(raw_answers)
            except Exception:
                raw_answers = []

        lat = request.data.get('lat') or None
        lng = request.data.get('lng') or None

        # Build field lookup
        fields_by_id = {str(f.id): f for f in form.fields.all()}

        # ── Validate required fields ──
        submitted_ids = {str(a.get('field_id', '')) for a in raw_answers if a.get('value') or a.get('field_id') in request.FILES}
        errors = {}
        for field in form.fields.all():
            if field.field_type == 'section':
                continue
            if field.is_required and str(field.id) not in submitted_ids:
                # Also check FILES for file fields
                if f"file_{field.id}" not in request.FILES:
                    errors[str(field.id)] = f'"{field.label}" is required.'

        if errors:
            return Response({'field_errors': errors}, status=400)

        # ── Create submission ──
        submission = FormSubmission.objects.create(
            form=form,
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            city=caller_city,
            state=caller_state,
            country=caller_country,
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            respondent_name=respondent_name,
            respondent_email=respondent_email,
            respondent=request.user if request.user.is_authenticated else None,
        )

        # ── Save answers ──
        for answer_data in raw_answers:
            field_id = str(answer_data.get('field_id', ''))
            field = fields_by_id.get(field_id)
            if not field or field.field_type == 'section':
                continue

            # Location restriction check
            if field.is_location_restricted:
                try:
                    lr = field.location_restriction
                    if not _check_location(
                        {'city': lr.city, 'state': lr.state, 'country': lr.country},
                        caller_city, caller_state, caller_country,
                    ):
                        logger.info(
                            f"[Forms] Skipping restricted field {field.id} "
                            f"for IP {ip} ({caller_city}, {caller_country})"
                        )
                        continue
                except FormFieldLocationRestriction.DoesNotExist:
                    pass

            value = answer_data.get('value')
            answer = SubmissionAnswer(
                submission=submission,
                field=field,
                field_label=field.label,
                field_type=field.field_type,
            )

            if field.field_type in ('short_text', 'long_text', 'email', 'phone', 'url', 'date', 'time', 'signature'):
                answer.text_value = str(value or '')
            elif field.field_type in ('number', 'rating', 'scale'):
                try:
                    answer.number_value = float(value)
                    answer.text_value = str(value)
                except (TypeError, ValueError):
                    pass
            elif field.field_type in ('dropdown', 'radio'):
                answer.text_value = str(value or '')
            elif field.field_type == 'checkbox':
                answer.json_value = value if isinstance(value, list) else [value] if value else []
                answer.text_value = ', '.join(answer.json_value) if answer.json_value else ''
            else:
                answer.text_value = str(value or '')

            answer.save()

        # ── Handle file uploads ──
        for key, file_obj in request.FILES.items():
            # key format: "file_<field_id>"
            if not key.startswith('file_'):
                continue
            field_id = key[5:]
            field = fields_by_id.get(field_id)
            if not field:
                continue

            if field.is_location_restricted:
                try:
                    lr = field.location_restriction
                    if not _check_location(
                        {'city': lr.city, 'state': lr.state, 'country': lr.country},
                        caller_city, caller_state, caller_country,
                    ):
                        continue
                except FormFieldLocationRestriction.DoesNotExist:
                    pass

            answer = SubmissionAnswer(
                submission=submission,
                field=field,
                field_label=field.label,
                field_type=field.field_type,
            )
            answer.file_value.save(file_obj.name, file_obj, save=False)
            answer.save()

        logger.info(
            f"[Forms] Submission {submission.id} for form {form.slug} "
            f"from {ip} ({caller_city}, {caller_country})"
        )

        return Response({
            'submission_id': str(submission.id),
            'message': form.confirmation_message,
            'redirect_url': form.confirmation_redirect_url or '',
        }, status=201)


# ──────────────────────────────────────────────────────────────────────────────
# QR Code generation for a form
# ──────────────────────────────────────────────────────────────────────────────

class FormGenerateQRView(APIView):
    """
    POST /api/v1/forms/<id>/generate-qr/
    Creates (or returns existing) QRCode pointing to /f/<slug>/.
    Returns { qr_id, qr_image_url, form_url }.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            form = Form.objects.get(id=pk, owner=request.user)
        except Form.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        form_url = request.build_absolute_uri(f"/f/{form.slug}/")

        try:
            from apps.qrcodes.models import QRCode
            from nanoid import generate as _nid

            if form.qr_slug:
                try:
                    qr = QRCode.objects.get(slug=form.qr_slug, created_by=request.user)
                    return Response({
                        'qr_id': str(qr.id),
                        'form_url': form_url,
                        'message': 'QR code already exists.',
                    })
                except QRCode.DoesNotExist:
                    pass

            slug = _nid('abcdefghijklmnopqrstuvwxyz0123456789', 8)
            qr = QRCode.objects.create(
                organization=request.user.organization,
                created_by=request.user,
                title=f"Form: {form.title}",
                slug=slug,
                qr_type='url',
                destination_url=form_url,
                status='active',
            )
            form.qr_slug = slug
            form.save(update_fields=['qr_slug'])

            return Response({
                'qr_id': str(qr.id),
                'form_url': form_url,
                'message': 'QR code created.',
            }, status=201)
        except Exception as e:
            logger.error(f"[Forms] QR generation error: {e}")
            return Response({'error': str(e)}, status=500)
