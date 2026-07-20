"""Centralized DRF exception handling for consistent error response shapes."""

import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger("nexivo")


def custom_exception_handler(exc, context):
    """
    Ensures every error response has a consistent shape:
    {"detail": "...", "code": "...", "errors": {...optional field errors...}}
    """

    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = drf_exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = drf_exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    response = drf_default_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception", exc_info=exc)
        return Response(
            {"detail": "An unexpected error occurred. Please try again.", "code": "internal_error"},
            status=500,
        )

    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        payload = {"detail": str(data["detail"]), "code": getattr(exc, "default_code", "error")}
    else:
        payload = {
            "detail": "Validation failed." if response.status_code == 400 else "Request failed.",
            "code": getattr(exc, "default_code", "error"),
            "errors": data,
        }

    response.data = payload
    return response
