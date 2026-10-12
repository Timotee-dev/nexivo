from django.db.models import Avg, Count

from reviews.models import Review


def recalculate_event_rating(event):
    """Recomputes Event.average_rating/review_count from approved reviews only."""
    agg = event.reviews.filter(moderation_status=Review.ModerationStatus.APPROVED).aggregate(
        avg=Avg("rating"), count=Count("id")
    )
    event.average_rating = round(agg["avg"] or 0, 2)
    event.review_count = agg["count"] or 0
    event.save(update_fields=["average_rating", "review_count"])


def customer_has_eligible_ticket(customer, event):
    """A customer may review an event only if they hold/held at least one ticket for it."""
    from tickets.models import Ticket
    return Ticket.objects.filter(
        holder=customer, event=event,
    ).exclude(status=Ticket.Status.CANCELLED).exists()
