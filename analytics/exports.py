"""CSV export generation for analytics data, per spec's 'Exports' requirement."""

import csv
import io


def export_to_csv(rows, fieldnames, filename="export.csv"):
    """Returns (content_bytes, filename) for a list-of-dicts dataset."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8"), filename


def export_bookings_csv(bookings_qs):
    rows = [
        {
            "booking_reference": b.booking_reference,
            "event": b.event.title,
            "customer_email": b.customer_email,
            "status": b.status,
            "total_amount": str(b.total_amount),
            "ticket_count": b.ticket_count,
            "created_at": b.created_at.isoformat(),
        }
        for b in bookings_qs.select_related("event")
    ]
    fieldnames = ["booking_reference", "event", "customer_email", "status", "total_amount", "ticket_count", "created_at"]
    return export_to_csv(rows, fieldnames, "bookings_export.csv")


def export_payments_csv(payments_qs):
    rows = [
        {
            "reference": p.gateway_reference,
            "gateway": p.gateway,
            "status": p.status,
            "amount": str(p.amount),
            "commission": str(p.platform_commission_amount),
            "host_payout": str(p.host_payout_amount),
            "paid_at": p.paid_at.isoformat() if p.paid_at else "",
        }
        for p in payments_qs
    ]
    fieldnames = ["reference", "gateway", "status", "amount", "commission", "host_payout", "paid_at"]
    return export_to_csv(rows, fieldnames, "payments_export.csv")
