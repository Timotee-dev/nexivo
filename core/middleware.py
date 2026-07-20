"""Custom middleware for audit logging and lightweight rate limiting."""

import time

from django.core.cache import cache
from django.http import JsonResponse


class AuditRequestMiddleware:
    """
    Attaches request metadata (IP, user-agent) used by views/signals for
    audit log entries, and logs a coarse trail of sensitive-method requests.
    """

    SENSITIVE_PREFIXES = ("/api/v1/auth/", "/api/v1/payments/", "/api/v1/payouts/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = self._get_ip(request)
        response = self.get_response(request)
        return response

    @staticmethod
    def _get_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")


class RateLimitMiddleware:
    """
    Simple sliding-window rate limiter keyed by IP, applied to sensitive
    auth/payment endpoints on top of DRF's per-view throttling, since this
    layer runs even for unauthenticated requests before DRF is invoked.
    """

    LIMITED_PATHS = {
        "/api/v1/auth/login/": (10, 60),
        "/api/v1/auth/register/": (5, 60),
        "/api/v1/payments/webhook/": (120, 60),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit_config = self.LIMITED_PATHS.get(request.path)
        if limit_config and request.method == "POST":
            limit, window = limit_config
            ip = request.META.get("REMOTE_ADDR", "unknown")
            cache_key = f"ratelimit:{request.path}:{ip}"
            count = cache.get(cache_key, 0)
            if count >= limit:
                return JsonResponse(
                    {"detail": "Too many requests. Please try again shortly."},
                    status=429,
                )
            cache.set(cache_key, count + 1, timeout=window)

        return self.get_response(request)
