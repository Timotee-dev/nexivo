"""
QR code image generation for tickets.
QR encodes a verification payload (ticket_code + integrity stamp).
Each QR has a "Powered by Nexivo" label baked into the image.
"""

import hashlib
import io

import qrcode
from PIL import Image, ImageDraw
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
    qr = qrcode.QRCode(
        box_size=8,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white").convert("RGB")

    qr_width, qr_height = qr_img.size
    branding_height = 24

    # Create canvas with branding strip at bottom
    final_img = Image.new("RGB", (qr_width, qr_height + branding_height), "white")
    final_img.paste(qr_img, (0, 0))

    # Gold branding strip
    draw = ImageDraw.Draw(final_img)
    draw.rectangle(
        [(0, qr_height), (qr_width, qr_height + branding_height)],
        fill="#C9A84C"
    )

    # Draw dots pattern as "Powered by Nexivo" using simple shapes
    # (avoids font dependency issues on different servers)
    text = "★ NEXIVO"
    try:
        from PIL import ImageFont
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 12)
            except Exception:
                font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (qr_width - text_w) // 2
        y = qr_height + (branding_height - text_h) // 2
        draw.text((x, y), text, fill="white", font=font)
    except Exception:
        pass

    buffer = io.BytesIO()
    final_img.save(buffer, format="PNG")
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"{ticket_code}.png")


def attach_qr_to_ticket(ticket):
    """Generates and saves the QR image onto a Ticket instance."""
    image_file = generate_qr_image(ticket.ticket_code)
    ticket.qr_image.save(image_file.name, image_file, save=True)
    return ticket