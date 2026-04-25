"""
API Response Helpers
====================
Standardized response envelope for all API endpoints.

Usage:
    from apps.core.responses import api_success, api_error, paginated_response

    # Success
    return api_success({"id": qr.id, "title": qr.title})

    # Error (prefer raising DRF exceptions so custom_exception_handler handles it)
    return api_error("QR code not found", status=404)

    # Paginated list
    return paginated_response(request, queryset, serializer_class)

Note: The custom_exception_handler in exceptions.py already normalizes all
error responses.  These helpers standardize the *success* side.
"""
from rest_framework.response import Response
from rest_framework import status as http_status


def api_success(data=None, message: str | None = None, status: int = http_status.HTTP_200_OK) -> Response:
    """
    Wrap successful data in a consistent envelope.

    Shape: { "success": true, "data": <data>, "message": <message> }
    """
    payload: dict = {"success": True}
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
    return Response(payload, status=status)


def api_error(message: str, code: str | None = None, status: int = http_status.HTTP_400_BAD_REQUEST) -> Response:
    """
    Return a structured error response without raising an exception.
    Prefer raising DRF exceptions (ValidationError, PermissionDenied, etc.)
    so the custom_exception_handler can handle them uniformly.  Use this
    only for edge-cases where you need fine-grained control.

    Shape: { "success": false, "error": { "code": <status>, "message": <msg> } }
    """
    payload: dict = {
        "success": False,
        "error": {
            "code": code or str(status),
            "message": message,
        }
    }
    return Response(payload, status=status)


def api_created(data=None, message: str | None = None) -> Response:
    """Convenience wrapper for 201 Created."""
    return api_success(data=data, message=message, status=http_status.HTTP_201_CREATED)
