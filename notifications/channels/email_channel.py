import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger("nexivo")


def send_email(*, to_email, subject, body, html_body=None, template=None, context=None):
    """
    Sends an email. If `template` is provided, renders it with `context`
    for the HTML version and strips tags for the plain-text fallback.
    Falls back to `html_body` if provided, or plain `body` otherwise.
    """
    try:
        if template and context:
            ctx = {"frontend_url": settings.FRONTEND_URL, **(context or {})}
            html_body = render_to_string(template, ctx)
            body = strip_tags(html_body)

        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        if html_body:
            email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True, None
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to_email, exc)
        return False, str(exc)