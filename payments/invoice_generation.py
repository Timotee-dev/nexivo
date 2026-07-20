"""Invoice PDF generation for completed payments, using ReportLab."""

import io

from django.core.files.base import ContentFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

GOLD = colors.HexColor("#d4af37")
BLACK = colors.HexColor("#0a0a0a")
DARK_GRAY = colors.HexColor("#333333")


def generate_invoice_pdf(payment) -> ContentFile:
    buffer = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    booking = payment.booking

    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, height - 25 * mm, "NEXIVO")
    c.setFillColor(GOLD)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 32 * mm, "INVOICE / RECEIPT")

    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 20 * mm, height - 25 * mm, f"Invoice #: {payment.gateway_reference}")
    c.drawRightString(width - 20 * mm, height - 30 * mm, f"Date: {payment.paid_at.strftime('%d %b %Y') if payment.paid_at else '-'}")

    y = height - 45 * mm
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Billed To")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y - 6 * mm, booking.customer_name)
    c.drawString(20 * mm, y - 12 * mm, booking.customer_email)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(110 * mm, y, "Event")
    c.setFont("Helvetica", 10)
    c.drawString(110 * mm, y - 6 * mm, booking.event.title[:40])
    c.drawString(110 * mm, y - 12 * mm, booking.event.start_datetime.strftime("%d %b %Y, %I:%M %p"))

    y -= 28 * mm
    c.setFillColor(colors.HexColor("#f0f0f0"))
    c.rect(20 * mm, y, width - 40 * mm, 8 * mm, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(22 * mm, y + 2.5 * mm, "Description")
    c.drawString(120 * mm, y + 2.5 * mm, "Qty")
    c.drawString(140 * mm, y + 2.5 * mm, "Unit Price")
    c.drawRightString(width - 22 * mm, y + 2.5 * mm, "Total")

    y -= 8 * mm
    c.setFont("Helvetica", 9)
    for item in booking.items.select_related("ticket_type"):
        c.drawString(22 * mm, y + 2 * mm, item.ticket_type.name)
        c.drawString(120 * mm, y + 2 * mm, str(item.quantity))
        c.drawString(140 * mm, y + 2 * mm, f"{item.unit_price}")
        c.drawRightString(width - 22 * mm, y + 2 * mm, f"{item.line_total}")
        y -= 7 * mm

    y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.line(110 * mm, y, width - 20 * mm, y)
    y -= 7 * mm

    def summary_line(label, value, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
        c.drawString(120 * mm, y, label)
        c.drawRightString(width - 22 * mm, y, f"{booking.currency} {value}")
        y -= 6 * mm

    summary_line("Subtotal", booking.subtotal)
    if booking.discount_amount:
        summary_line("Discount", f"-{booking.discount_amount}")
    summary_line("Processing Fee", booking.processing_fee)
    summary_line("Total Paid", booking.total_amount, bold=True)

    c.setFont("Helvetica", 8)
    c.setFillColor(DARK_GRAY)
    c.drawString(20 * mm, 20 * mm, f"Payment method: {payment.gateway.title()}")
    c.drawString(20 * mm, 15 * mm, f"Transaction ID: {payment.gateway_transaction_id or '-'}")
    c.drawString(20 * mm, 10 * mm, "Thank you for using Nexivo.")

    c.showPage()
    c.save()
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"invoice_{payment.gateway_reference}.pdf")
