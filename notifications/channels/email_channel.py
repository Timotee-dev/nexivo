import logging
import requests

from django.conf import settings

logger = logging.getLogger("nexivo")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(*, to_email, subject, body, html_body=None, template=None, context=None, attachments=None):
    """
    Sends email via Brevo HTTP API instead of SMTP.
    Bypasses Render's port 587 block.
    """
    try:
        if template and context:
            from django.template.loader import render_to_string
            from django.utils.html import strip_tags
            ctx = {"frontend_url": settings.FRONTEND_URL, **(context or {})}
            html_body = render_to_string(template, ctx)
            body = strip_tags(html_body)

        api_key = getattr(settings, 'BREVO_API_KEY', '')
        if not api_key:
            logger.error("NEXIVO EMAIL: BREVO_API_KEY not set")
            return False, "BREVO_API_KEY not configured"

        payload = {
            "sender": {"name": "Nexivo", "email": "teetimo29@gmail.com"},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        }

        if html_body:
            payload["htmlContent"] = html_body

        if attachments:
            payload["attachment"] = [
                {
                    "name": fname,
                    "content": __import__('base64').b64encode(fcontent).decode('utf-8'),
                }
                for fname, fcontent, fmime in attachments
            ]

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        }

        logger.info("NEXIVO EMAIL: Sending to %s via Brevo API", to_email)
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=15)

        if response.status_code in (200, 201):
            logger.info("NEXIVO EMAIL: Successfully sent to %s", to_email)
            return True, None
        else:
            logger.error("NEXIVO EMAIL: Failed to %s — %s %s", to_email, response.status_code, response.text)
            return False, response.text

    except Exception as exc:
        logger.exception("NEXIVO EMAIL: Exception sending to %s — %s", to_email, exc)
        return False, str(exc)