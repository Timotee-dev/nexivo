"""
PDF ticket generation using ReportLab. Produces one page per ticket with:
  - Nexivo branding header
  - Event name, date, venue/platform
  - Holder name and ticket type
  - Unique QR code image embedded
  - Unique barcode (Code128) embedded
  - Booking reference and ticket code in footer
"""

import io
import os

from django.core.files.base import ContentFile


def generate_ticket_pdf(ticket) -> ContentFile:
    """
    Generates a PDF for a single ticket and returns it as a ContentFile
    ready to be saved to ticket.pdf_file.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # --- Header bar ---
    header_style = ParagraphStyle(
        "NexivoHeader", parent=styles["Heading1"],
        textColor=colors.white, fontSize=24, spaceAfter=0,
    )
    header_data = [[Paragraph("NEXIVO", header_style), Paragraph("E-TICKET", header_style)]]
    header_table = Table(header_data, colWidths=["60%", "40%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5*cm))

    # --- Event details ---
    event = ticket.event
    start = event.start_datetime.strftime("%A, %d %B %Y at %H:%M")
    location = (
        f"{event.venue_name}, {event.city}" if event.is_physical
        else f"Online — {event.virtual_platform}"
    )

    title_style = ParagraphStyle("EventTitle", parent=styles["Heading2"], fontSize=18, spaceAfter=4)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#555555"))
    bold_style = ParagraphStyle("Bold", parent=styles["Normal"], fontSize=12, fontName="Helvetica-Bold")

    elements.append(Paragraph(event.title, title_style))
    elements.append(Paragraph(start, sub_style))
    elements.append(Paragraph(location, sub_style))
    elements.append(Spacer(1, 0.4*cm))

    # --- Ticket details row (left info + right QR) ---
    info_data = [
        [Paragraph("<b>Ticket Type:</b>", styles["Normal"]), Paragraph(ticket.ticket_type.name, bold_style)],
        [Paragraph("<b>Holder:</b>", styles["Normal"]), Paragraph(ticket.holder_name, bold_style)],
        [Paragraph("<b>Booking Ref:</b>", styles["Normal"]), Paragraph(ticket.booking_item.booking.booking_reference, bold_style)],
        [Paragraph("<b>Ticket Code:</b>", styles["Normal"]), Paragraph(ticket.ticket_code, bold_style)],
    ]
    info_table = Table(info_data, colWidths=["35%", "65%"])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#F8F8F8"), colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    # --- QR code ---
    qr_image_field = ticket.qr_image
    if qr_image_field and qr_image_field.name:
        try:
            qr_img = Image(qr_image_field.path, width=4*cm, height=4*cm)
        except Exception:
            qr_img = Paragraph("QR unavailable", styles["Normal"])
    else:
        from tickets.qr import generate_qr_image
        qr_file = generate_qr_image(ticket.ticket_code)
        qr_img = Image(io.BytesIO(qr_file.read()), width=4*cm, height=4*cm)

    main_table = Table(
        [[info_table, qr_img]],
        colWidths=["70%", "30%"]
    )
    main_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 0.4*cm))

    # --- Barcode ---
    barcode_img = _make_barcode_image(ticket.barcode_value)
    if barcode_img:
        elements.append(barcode_img)
        elements.append(Spacer(1, 0.2*cm))

    # --- Divider + Terms ---
    elements.append(Spacer(1, 0.3*cm))
    divider_table = Table([[""]], colWidths=["100%"])
    divider_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(divider_table)
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(
        "This ticket is valid for one entry only. Do not share your QR code. "
        "Nexivo is not responsible for lost or stolen tickets.",
        ParagraphStyle("Fine", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    ))

    doc.build(elements)
    buffer.seek(0)
    filename = f"ticket-{ticket.ticket_code}.pdf"
    return ContentFile(buffer.read(), name=filename)


def _make_barcode_image(barcode_value):
    """Generate a Code128 barcode image using reportlab's built-in barcode support."""
    try:
        from reportlab.graphics.barcode import code128
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF, renderSVG
        import io

        barcode = code128.Code128(barcode_value, barHeight=1.2*28.35, barWidth=1.0)
        # Wrap in a Drawing for embedding
        drawing_width = barcode.width + 20
        drawing_height = barcode.height + 10
        drawing = Drawing(drawing_width, drawing_height)
        drawing.add(barcode)
        buf = io.BytesIO()

        from reportlab.lib.units import cm
        from reportlab.platypus import Image as RLImage

        # Render barcode to PNG via pillow path
        from reportlab.graphics import renderPM
        renderPM.drawToFile(drawing, buf, fmt="PNG")
        buf.seek(0)
        return RLImage(buf, width=6*cm, height=1.2*cm)
    except Exception:
        return None


def attach_pdf_to_ticket(ticket):
    """Generates and saves the PDF onto the Ticket instance. Idempotent."""
    pdf_file = generate_ticket_pdf(ticket)
    ticket.pdf_file.save(pdf_file.name, pdf_file, save=True)
    return ticket
