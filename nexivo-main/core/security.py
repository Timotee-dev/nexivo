"""
Security utilities: CAPTCHA verification, brute-force rate limiting
(in addition to django-axes which handles DB-backed lockout), and
request validation helpers.
"""

import hashlib
import logging
import time
from functools import wraps

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response

logger = logging.getLogger("nexivo")

# ── hCaptcha / reCAPTCHA ────────────────────────────────────────────────

def verify_captcha(token: str, remote_ip: str = "") -> bool:
    """
    Verifies an hCaptcha or reCAPTCHA v2 token server-side.
    Set CAPTCHA_PROVIDER = 'hcaptcha' or 'recaptcha' in settings.
    Set CAPTCHA_SECRET_KEY to your secret.
    Returns True immediately (skipping network call) in DEBUG mode
    so local dev isn't blocked on real captcha tokens.
    """
    if settings.DEBUG:
        return True

    provider = getattr(settings, "CAPTCHA_PROVIDER", "hcaptcha")
    secret = getattr(settings, "CAPTCHA_SECRET_KEY", "")

    if not secret or not token:
        logger.warning("CAPTCHA_SECRET_KEY not configured or empty token — skipping verification")
        return True

    urls = {
        "hcaptcha":  "https://hcaptcha.com/siteverify",
        "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
    }
    url = urls.get(provider, urls["hcaptcha"])

    try:
        resp = requests.post(url, data={"secret": secret, "response": token, "remoteip": remote_ip}, timeout=8)
        return resp.json().get("success", False)
    except Exception as exc:
        logger.error("CAPTCHA verification request failed: %s", exc)
        return False


# ── Rate limiting helpers ────────────────────────────────────────────────

def get_rate_limit_key(action: str, identifier: str) -> str:
    h = hashlib.sha1(identifier.encode()).hexdigest()[:12]
    return f"ratelimit:{action}:{h}"


def check_rate_limit(action: str, identifier: str, limit: int, window: int) -> tuple[bool, int]:
    """
    Sliding-window rate check. Returns (allowed, remaining).
    identifier: IP address, email, or user ID — whatever makes sense for the action.
    """
    key = get_rate_limit_key(action, identifier)
    current = cache.get(key, 0)
    if current >= limit:
        return False, 0
    cache.set(key, current + 1, timeout=window)
    return True, limit - current - 1


def rate_limit(action: str, limit: int, window: int, identifier_func=None):
    """
    DRF view decorator for endpoint-level rate limiting beyond DRF's
    built-in throttling. Uses IP by default; pass identifier_func(request)
    to key on something else (e.g. email).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(self_or_request, request=None, *args, **kwargs):
            req = request if request is not None else self_or_request
            identifier = identifier_func(req) if identifier_func else (
                req.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or req.META.get("REMOTE_ADDR", "unknown")
            )
            allowed, remaining = check_rate_limit(action, identifier, limit, window)
            if not allowed:
                return Response(
                    {"detail": f"Too many {action} attempts. Please wait before trying again.", "code": "rate_limited"},
                    status=429,
                )
            if request is not None:
                return view_func(self_or_request, request, *args, **kwargs)
            return view_func(self_or_request, *args, **kwargs)
        return wrapper
    return decorator
