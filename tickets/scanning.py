"""
Core check-in/scan validation logic. Used by both the live scanner endpoint
and the offline-sync batch-replay endpoint, so duplicate-prevention behaves
identically whether a scan arrives in real time or hours later from a
device that just reconnected.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from tickets.models import Ticket, TicketScanLog
from tickets.qr import verify_qr_payload


@transaction.atomic
def process_scan(*, event, code, scanned_by, client_scanned_at=None, device_id=None, was_offline_sync=False):
    """
    Validates a scanned code against the database and records the attempt.
    Returns a dict: {result, message, ticket, checked_in_at, previously_scanned_by}

    Duplicate prevention: a ticket can only transition VALID -> USED once.
    select_for_update() locks the row so two near-simultaneous scans of the
    same QR (e.g. two scanners at different doors) cannot both succeed.
    """

    # The QR encodes "ticket_code.integrity_stamp"; raw barcode scans are
    # plain numeric codes with no stamp, so try QR verification first and
    # fall back to treating the raw value as a ticket_code or barcode_value.
    ticket_code = verify_qr_payload(code) or code

    try:
        ticket = (
            Ticket.objects.select_for_update()
            .select_related("event", "ticket_type")
            .get(Q(ticket_code=ticket_code) | Q(barcode_value=ticket_code))
        )
    except Ticket.DoesNotExist:
        _log_scan(event, code, TicketScanLog.Result.INVALID, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket=None)
        return {
            "result": TicketScanLog.Result.INVALID,
            "message": "Ticket code not recognized.",
            "ticket": None,
            "checked_in_at": None,
            "previously_scanned_by": None,
        }

    if ticket.event_id != event.id:
        _log_scan(event, code, TicketScanLog.Result.WRONG_EVENT, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket=ticket)
        return {
            "result": TicketScanLog.Result.WRONG_EVENT,
            "message": f"This ticket belongs to a different event ('{ticket.event.title}').",
            "ticket": ticket,
            "checked_in_at": None,
            "previously_scanned_by": None,
        }

    if ticket.status in (Ticket.Status.CANCELLED, Ticket.Status.REFUNDED):
        _log_scan(event, code, TicketScanLog.Result.CANCELLED_TICKET, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket=ticket)
        return {
            "result": TicketScanLog.Result.CANCELLED_TICKET,
            "message": f"This ticket has been {ticket.status} and is no longer valid.",
            "ticket": ticket,
            "checked_in_at": None,
            "previously_scanned_by": None,
        }

    if ticket.status == Ticket.Status.USED:
        _log_scan(event, code, TicketScanLog.Result.DUPLICATE, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket=ticket)
        return {
            "result": TicketScanLog.Result.DUPLICATE,
            "message": f"Already checked in at {ticket.checked_in_at:%H:%M:%S} by "
                       f"{ticket.checked_in_by.username if ticket.checked_in_by else 'unknown'}.",
            "ticket": ticket,
            "checked_in_at": ticket.checked_in_at,
            "previously_scanned_by": ticket.checked_in_by.username if ticket.checked_in_by else None,
        }

    # Valid, not yet used -> check in now.
    check_in_time = client_scanned_at if (was_offline_sync and client_scanned_at) else timezone.now()
    ticket.status = Ticket.Status.USED
    ticket.checked_in_at = check_in_time
    ticket.checked_in_by = scanned_by
    ticket.save(update_fields=["status", "checked_in_at", "checked_in_by"])

    _log_scan(event, code, TicketScanLog.Result.SUCCESS, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket=ticket)

    return {
        "result": TicketScanLog.Result.SUCCESS,
        "message": f"Checked in: {ticket.holder_name} ({ticket.ticket_type.name}).",
        "ticket": ticket,
        "checked_in_at": check_in_time,
        "previously_scanned_by": None,
    }


def _log_scan(event, scanned_code, result, scanned_by, client_scanned_at, device_id, was_offline_sync, ticket):
    TicketScanLog.objects.create(
        ticket=ticket,
        event=event,
        scanned_code=scanned_code[:40],
        result=result,
        scanned_by=scanned_by,
        client_scanned_at=client_scanned_at,
        was_offline_sync=was_offline_sync,
        device_id=device_id,
    )
