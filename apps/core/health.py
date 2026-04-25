"""
Health Check Endpoints
=======================
Liveness + readiness probes for container orchestration and load balancers.
Each microservice exposes /health/ independently.
"""
import time
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    GET /health/
    Returns 200 if service is alive with subsystem status.
    Used by Docker HEALTHCHECK, Kubernetes probes, and load balancers.
    """

    def get(self, request):
        checks = {}
        overall = True

        # Database check
        try:
            start = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks['database'] = {
                'status': 'healthy',
                'latency_ms': round((time.time() - start) * 1000, 1),
            }
        except Exception as e:
            checks['database'] = {'status': 'unhealthy'}
            # Error details intentionally omitted — may contain DB credentials
            overall = False

        # Cache check
        try:
            start = time.time()
            cache.set('_health_check', '1', timeout=10)
            val = cache.get('_health_check')
            checks['cache'] = {
                'status': 'healthy' if val == '1' else 'degraded',
                'latency_ms': round((time.time() - start) * 1000, 1),
            }
        except Exception:
            checks['cache'] = {'status': 'unhealthy'}
            # Error details intentionally omitted
            overall = False

        return JsonResponse({
            'status': 'healthy' if overall else 'unhealthy',
            'service': 'qrgenie',
            'checks': checks,
        }, status=200 if overall else 503)
