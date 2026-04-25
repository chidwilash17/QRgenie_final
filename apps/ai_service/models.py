"""
AI Service — Models
=====================
Tracks AI generation requests, token usage, and cached results.
"""
import uuid
from django.db import models
from django.conf import settings


class AIGenerationLog(models.Model):
    """Log every AI API call for auditing and token tracking."""
    GENERATION_TYPE_CHOICES = [
        ('landing_page', 'Landing Page Generation'),
        ('analytics_summary', 'Analytics Summary'),
        ('route_suggestion', 'Smart Route Suggestion'),
        ('anomaly_detection', 'Anomaly Detection'),
        ('ab_optimizer', 'A/B Test Optimizer'),
        ('qr_description', 'QR Description Generator'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='ai_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    generation_type = models.CharField(max_length=50, choices=GENERATION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Request
    prompt = models.TextField()
    model_used = models.CharField(max_length=100, default='gpt-4o')
    temperature = models.FloatField(default=0.7)

    # Response
    result = models.JSONField(default=dict, blank=True)
    raw_response = models.TextField(blank=True, default='')

    # Usage
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)

    # Linked resource
    qr_code = models.ForeignKey(
        'qrcodes.QRCode', on_delete=models.SET_NULL, null=True, blank=True
    )

    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['generation_type']),
        ]

    def __str__(self):
        return f"{self.generation_type} — {self.status}"
