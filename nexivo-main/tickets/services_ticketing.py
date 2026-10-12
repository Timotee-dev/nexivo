"""Ticket-generation logic, separated from the QR module to avoid circular imports
between bookings -> tickets -> events."""

from django.db import transaction

from tickets.models import Ticket
from tickets.pdf_generation import attach_pdf_to_ticket
from tickets.qr import attach_qr_to_ticket


@transaction.atomic
def generate_tickets_for_booking(booking):
    """
    Creates one Ticket row per unit purchased across all booking items,
    each with its own unique QR code. Idempotent — if tickets already
    exist for this booking (e.g. webhook fired twice), does nothing further.
    """
    if Ticket.objects.filter(booking_item__booking=booking).exists():
        return list(Ticket.objects.filter(booking_item__booking=booking))

    created = []
    for item in booking.items.select_related("ticket_type", "booking__event"):
        for _ in range(item.quantity):
            ticket = Ticket.objects.create(
                booking_item=item,
                event=item.ticket_type.event,
                ticket_type=item.ticket_type,
                holder=booking.customer,
                holder_name=booking.customer_name,
                holder_email=booking.customer_email,
            )
            attach_qr_to_ticket(ticket)
            attach_pdf_to_ticket(ticket)
            created.append(ticket)

    return created
