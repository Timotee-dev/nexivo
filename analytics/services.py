"""
Analytics data computation for host and super-admin dashboards.
All queries use the existing transactional tables — no separate analytics DB
needed at Nexivo's current scale. Heavy queries are annotated with caching
hints so views can cache results for N minutes in production.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone


def host_dashboard(host):
    """All key metrics a host needs on their dashboard overview."""
    from bookings.models import Booking
    from events.models import Event
    from payments.models import Payment
    from tickets.models import Ticket

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    events_qs = Event.objects.filter(host=host)
    bookings_qs = Booking.objects.filter(event__host=host, status=Booking.Status.CONFIRMED)
    payments_qs = Payment.objects.filter(booking__event__host=host, status=Payment.Status.SUCCESSFUL)

    total_revenue = payments_qs.aggregate(total=Sum("host_payout_amount"))["total"] or Decimal("0")
    revenue_30d = payments_qs.filter(paid_at__gte=thirty_days_ago).aggregate(
        total=Sum("host_payout_amount"))["total"] or Decimal("0")

    revenue_by_day = list(
        payments_qs.filter(paid_at__gte=thirty_days_ago)
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(revenue=Sum("host_payout_amount"), sales=Count("id"))
        .order_by("day")
    )

    top_events = list(
        events_qs.filter(status=Event.Status.PUBLISHED)
        .annotate(
            revenue=Sum(
                "bookings__payments__host_payout_amount",
                filter=Q(bookings__payments__status=Payment.Status.SUCCESSFUL)
            )
        )
        .order_by(F("revenue").desc(nulls_last=True))[:5]
        .values("id", "title", "tickets_sold_count", "revenue", "average_rating", "start_datetime")
    )

    tickets_by_type = list(
        Ticket.objects.filter(event__host=host, status__in=["valid", "used"])
        .values("ticket_type__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    upcoming = events_qs.filter(status=Event.Status.PUBLISHED, start_datetime__gte=now).count()
    past = events_qs.filter(end_datetime__lt=now).count()

    total_attendees = Ticket.objects.filter(event__host=host, status=Ticket.Status.USED).count()
    attendance_rate = 0
    total_sold = Ticket.objects.filter(event__host=host).exclude(status="cancelled").count()
    if total_sold > 0:
        attendance_rate = round((total_attendees / total_sold) * 100, 1)

    return {
        "total_events": events_qs.count(),
        "upcoming_events": upcoming,
        "past_events": past,
        "total_bookings": bookings_qs.count(),
        "total_tickets_sold": total_sold,
        "total_attendees": total_attendees,
        "attendance_rate_percent": attendance_rate,
        "total_revenue": str(total_revenue),
        "revenue_last_30_days": str(revenue_30d),
        "average_rating": str(
            events_qs.aggregate(avg=Avg("average_rating"))["avg"] or 0
        ),
        "total_reviews": events_qs.aggregate(reviews=Sum("review_count"))["reviews"] or 0,
        "revenue_by_day": [
            {"day": r["day"].isoformat(), "revenue": str(r["revenue"]), "sales": r["sales"]}
            for r in revenue_by_day
        ],
        "top_events": [
            {
                "id": str(e["id"]),
                "title": e["title"],
                "tickets_sold": e["tickets_sold_count"],
                "revenue": str(e["revenue"] or 0),
                "rating": str(e["average_rating"]),
                "date": e["start_datetime"].isoformat(),
            }
            for e in top_events
        ],
        "tickets_by_type": [
            {"type": t["ticket_type__name"], "count": t["count"]}
            for t in tickets_by_type
        ],
    }


def event_analytics(event):
    """Per-event deep analytics for a host."""
    from bookings.models import Booking
    from payments.models import Payment
    from tickets.models import Ticket, TicketScanLog

    bookings = Booking.objects.filter(event=event)
    payments = Payment.objects.filter(booking__event=event, status=Payment.Status.SUCCESSFUL)

    total_revenue = payments.aggregate(t=Sum("host_payout_amount"))["t"] or Decimal("0")
    refunded = payments.filter(
        status__in=[Payment.Status.REFUNDED, Payment.Status.PARTIALLY_REFUNDED]
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    tickets_sold = Ticket.objects.filter(event=event).exclude(status="cancelled").count()
    tickets_used = Ticket.objects.filter(event=event, status=Ticket.Status.USED).count()
    tickets_remaining = event.total_tickets_remaining

    scan_log = TicketScanLog.objects.filter(event=event)
    successful_scans = scan_log.filter(result=TicketScanLog.Result.SUCCESS).count()
    duplicate_scans = scan_log.filter(result=TicketScanLog.Result.DUPLICATE).count()

    sales_over_time = list(
        bookings.filter(status=Booking.Status.CONFIRMED)
        .annotate(day=TruncDate("confirmed_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )

    return {
        "event_id": str(event.id),
        "title": event.title,
        "total_capacity": event.total_tickets_available,
        "tickets_sold": tickets_sold,
        "tickets_remaining": tickets_remaining,
        "checked_in": tickets_used,
        "attendance_rate": round((tickets_used / tickets_sold * 100), 1) if tickets_sold else 0,
        "total_revenue": str(total_revenue),
        "total_refunded": str(refunded),
        "total_bookings": bookings.count(),
        "confirmed_bookings": bookings.filter(status=Booking.Status.CONFIRMED).count(),
        "cancelled_bookings": bookings.filter(status=Booking.Status.CANCELLED).count(),
        "average_rating": str(event.average_rating),
        "review_count": event.review_count,
        "successful_scans": successful_scans,
        "duplicate_scan_attempts": duplicate_scans,
        "sales_over_time": [
            {"day": r["day"].isoformat(), "bookings": r["count"]}
            for r in sales_over_time
        ],
    }


def platform_dashboard():
    """Super-admin platform-wide analytics overview."""
    from accounts.models import User
    from bookings.models import Booking
    from events.models import Event
    from payments.models import Payment

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    payments_qs = Payment.objects.filter(status=Payment.Status.SUCCESSFUL)
    total_gmv = payments_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    total_platform_revenue = payments_qs.aggregate(
        t=Sum("platform_commission_amount"))["t"] or Decimal("0")
    total_host_payouts = payments_qs.aggregate(
        t=Sum("host_payout_amount"))["t"] or Decimal("0")

    gmv_30d = payments_qs.filter(paid_at__gte=thirty_days_ago).aggregate(
        t=Sum("amount"))["t"] or Decimal("0")
    revenue_30d = payments_qs.filter(paid_at__gte=thirty_days_ago).aggregate(
        t=Sum("platform_commission_amount"))["t"] or Decimal("0")

    revenue_by_month = list(
        payments_qs.annotate(month=TruncMonth("paid_at"))
        .values("month")
        .annotate(gmv=Sum("amount"), platform_cut=Sum("platform_commission_amount"))
        .order_by("month")
    )

    from payments.models import Refund
    total_refunded = Refund.objects.filter(
        status=Refund.Status.COMPLETED
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    total_users = User.objects.count()
    new_users_30d = User.objects.filter(created_at__gte=thirty_days_ago).count()
    total_hosts = User.objects.filter(role=User.Role.HOST).count()
    total_customers = User.objects.filter(role=User.Role.CUSTOMER).count()

    total_events = Event.objects.count()
    live_events = Event.objects.filter(
        status=Event.Status.PUBLISHED, end_datetime__gte=now
    ).count()

    from disputes.models import Dispute
    open_disputes = Dispute.objects.filter(
        status__in=[Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW]
    ).count()

    return {
        "total_gmv": str(total_gmv),
        "total_platform_revenue": str(total_platform_revenue),
        "total_host_payouts": str(total_host_payouts),
        "total_refunded": str(total_refunded),
        "gmv_last_30_days": str(gmv_30d),
        "platform_revenue_last_30_days": str(revenue_30d),
        "total_users": total_users,
        "new_users_30_days": new_users_30d,
        "total_hosts": total_hosts,
        "total_customers": total_customers,
        "total_events": total_events,
        "live_events": live_events,
        "total_bookings": Booking.objects.count(),
        "total_tickets_sold": Payment.objects.filter(
            status=Payment.Status.SUCCESSFUL
        ).aggregate(t=Sum("booking__items__quantity"))["t"] or 0,
        "open_disputes": open_disputes,
        "revenue_by_month": [
            {
                "month": r["month"].strftime("%Y-%m"),
                "gmv": str(r["gmv"]),
                "platform_cut": str(r["platform_cut"]),
            }
            for r in revenue_by_month
        ],
    }


def export_bookings_csv(event):
    """Returns a CSV string of all confirmed bookings for an event (host report)."""
    import csv, io
    from bookings.models import Booking

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Booking Ref", "Customer Name", "Customer Email", "Customer Phone",
        "Ticket Types", "Quantity", "Total Paid", "Status", "Confirmed At",
    ])
    for booking in Booking.objects.filter(event=event).select_related("customer").prefetch_related("items__ticket_type"):
        items_summary = "; ".join(f"{i.quantity}x {i.ticket_type.name}" for i in booking.items.all())
        writer.writerow([
            booking.booking_reference,
            booking.customer_name,
            booking.customer_email,
            booking.customer_phone or "",
            items_summary,
            booking.ticket_count,
            str(booking.total_amount),
            booking.status,
            booking.confirmed_at.isoformat() if booking.confirmed_at else "",
        ])
    return output.getvalue()
