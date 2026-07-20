"""
QR code + barcode image generation for tickets.
QR encodes a verification payload (ticket_code + a short integrity stamp)
that the scanner endpoint validates; the rendered PNG is stored on the
Ticket so it can be embedded directly into the PDF ticket.
"""

import hashlib
import io

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile


def _integrity_stamp(ticket_code: str) -> str:
    """Short HMAC-like stamp so a scanned QR can't be trivially forged by
    guessing a ticket_code format; full validation still happens server-side
    against the DB, this is just a cheap pre-check."""
    raw = f"{ticket_code}:{settings.SECRET_KEY}".encode()
    return hashlib.sha256(raw).hexdigest()[:10]


def build_qr_payload(ticket_code: str) -> str:
    return f"{ticket_code}.{_integrity_stamp(ticket_code)}"


def verify_qr_payload(payload: str) -> str | None:
    """Returns the ticket_code if the integrity stamp matches, else None."""
    try:
        code, stamp = payload.rsplit(".", 1)
    except ValueError:
        return None
    if _integrity_stamp(code) == stamp:
        return code
    return None


def generate_qr_image(ticket_code: str) -> ContentFile:
    payload = build_qr_payload(ticket_code)
    img = qrcode.make(payload, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"{ticket_code}.png")


def attach_qr_to_ticket(ticket):
    """Generates and saves the QR image onto a Ticket instance."""
    image_file = generate_qr_image(ticket.ticket_code)
    ticket.qr_image.save(image_file.name, image_file, save=True)
    return ticket
