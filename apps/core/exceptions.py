"""
Custom Exception Handler
=========================
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger('apps.core')


def custom_exception_handler(exc, context):
    """Global API exception handler with structured error responses."""
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            'error': True,
            'status_code': response.status_code,
            'detail': response.data,
        }
        # Flatten simple detail messages
        if isinstance(response.data, dict) and 'detail' in response.data:
            error_data['message'] = str(response.data['detail'])
        elif isinstance(response.data, list):
            error_data['message'] = response.data[0] if response.data else 'An error occurred.'
        else:
            error_data['message'] = 'Validation error.'
            error_data['errors'] = response.data

        response.data = error_data
    else:
        # Unhandled exception
        logger.exception(f"Unhandled exception: {exc}", exc_info=exc)
        response = Response({
            'error': True,
            'status_code': 500,
            'message': 'An internal server error occurred.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response
