"""
QR code + barcode image generation for tickets.
QR encodes a verification payload (ticket_code + a short integrity stamp)
that the scanner endpoint validates; the rendered PNG is stored on the
Ticket so it can be embedded directly into the PDF ticket.
"""

import hashlib
import io

import qrcode
from qrcode.image.styledpil import StyledPilImage
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.files.base import ContentFile


def _integrity_stamp(ticket_code: str) -> str:
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

    # Generate QR code
    qr = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Add "Powered by Nexivo" branding below the QR
    qr_width, qr_height = qr_img.size
    branding_height = 28
    total_height = qr_height + branding_height

    # Create new image with white background
    final_img = Image.new("RGB", (qr_width, total_height), "white")
    final_img.paste(qr_img, (0, 0))

    # Add branding text
    draw = ImageDraw.Draw(final_img)
    text = "Powered by Nexivo"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
    except Exception:
        font = ImageFont.load_default()

    # Center the text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (qr_width - text_width) // 2
    text_y = qr_height + 6

    # Draw gold/yellow background for branding strip
    draw.rectangle([(0, qr_height), (qr_width, total_height)], fill="#C9A84C")
    draw.text((text_x, text_y), text, fill="white", font=font)

    buffer = io.BytesIO()
    final_img.save(buffer, format="PNG")
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"{ticket_code}.png")


def attach_qr_to_ticket(ticket):
    """Generates and saves the QR image onto a Ticket instance."""
    image_file = generate_qr_image(ticket.ticket_code)
    ticket.qr_image.save(image_file.name, image_file, save=True)
    return ticket