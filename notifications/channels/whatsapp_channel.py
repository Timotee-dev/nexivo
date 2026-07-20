"""
WhatsApp delivery via a generic HTTP provider (e.g. Meta WhatsApp Cloud API,
Twilio, or a local aggregator). Configured via WHATSAPP_API_URL/TOKEN so the
actual provider can be swapped without touching call sites.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger("nexivo")


def send_whatsapp(*, to_phone, message):
    if not settings.WHATSAPP_API_URL or not to_phone:
        logger.info("WhatsApp not configured or no phone number; skipping send to %s", to_phone)
        return False, "WhatsApp provider not configured or recipient has no phone number."

    try:
        response = requests.post(
            settings.WHATSAPP_API_URL,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}"},
            json={"to": to_phone, "type": "text", "text": {"body": message}},
            timeout=15,
        )
        if response.status_code >= 400:
            return False, f"WhatsApp provider error {response.status_code}: {response.text[:300]}"
        return True, None
    except requests.RequestException as exc:
        logger.exception("Failed to send WhatsApp message to %s", to_phone)
        return False, str(exc)
