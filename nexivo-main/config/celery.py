"""
Celery application instance for Nexivo.
Workers are started with: celery -A config worker -l info
Beat scheduler: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""

import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("nexivo")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ── Scheduled tasks ────────────────────────────────────────────────────
@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    from celery.schedules import crontab

    # Expire stale pending bookings every 2 minutes
    sender.add_periodic_task(120.0, expire_stale_bookings_task.s(), name="expire-stale-bookings")

    # Run automatic payout scheduling every hour
    sender.add_periodic_task(3600.0, schedule_payouts_task.s(), name="schedule-host-payouts")

    # Daily reconciliation at 02:00 Africa/Lagos
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        run_reconciliation_task.s(),
        name="daily-reconciliation",
    )

    # 24h event reminders: check every 15 minutes
    sender.add_periodic_task(900.0, send_event_reminders_task.s(), name="event-reminders")


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def expire_stale_bookings_task(self):
    try:
        from bookings.services import expire_stale_bookings
        count = expire_stale_bookings()
        return {"expired": count}
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def schedule_payouts_task(self):
    try:
        from payouts.services import schedule_due_payouts
        payouts = schedule_due_payouts()
        return {"scheduled": len(payouts)}
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=2)
def run_reconciliation_task(self):
    try:
        from payments.reconciliation import reconcile_all_gateways
        return reconcile_all_gateways()
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def send_event_reminders_task(self):
    """Send 24h-before reminders for events starting in the next 25 hours."""
    try:
        from django.utils import timezone
        from bookings.models import Booking
        from notifications.services import notify_event_reminder

        window_start = timezone.now() + timezone.timedelta(hours=23)
        window_end   = timezone.now() + timezone.timedelta(hours=25)

        upcoming = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            event__start_datetime__gte=window_start,
            event__start_datetime__lte=window_end,
        ).select_related("event", "customer")

        count = 0
        for booking in upcoming:
            notify_event_reminder(booking)
            count += 1
        return {"reminders_sent": count}
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Async notification tasks (replace synchronous calls) ────────────────

@app.task(bind=True, max_retries=5, default_retry_delay=30)
def notify_async(self, trigger_name: str, **kwargs):
    """
    Generic async notification dispatcher. trigger_name maps to a function
    in notifications.services. Object IDs are passed as kwargs and
    re-fetched inside the task to avoid serialising full model instances.
    """
    try:
        from notifications import services
        trigger = getattr(services, trigger_name, None)
        if not trigger:
            return {"error": f"Unknown trigger: {trigger_name}"}

        # Resolve model instances from IDs
        resolved = _resolve_objects(kwargs)
        trigger(**resolved)
        return {"triggered": trigger_name}
    except Exception as exc:
        raise self.retry(exc=exc)


def _resolve_objects(kwargs: dict) -> dict:
    from bookings.models import Booking
    from payments.models import Payment, Refund
    from payouts.models import Payout
    from tickets.models import TicketTransfer
    from accounts.models import HostProfile

    resolved = {}
    if "booking_id" in kwargs:
        resolved["booking"] = Booking.objects.get(pk=kwargs["booking_id"])
    if "payment_id" in kwargs:
        resolved["payment"] = Payment.objects.get(pk=kwargs["payment_id"])
    if "refund_id" in kwargs:
        resolved["refund"] = Refund.objects.get(pk=kwargs["refund_id"])
    if "payout_id" in kwargs:
        resolved["payout"] = Payout.objects.get(pk=kwargs["payout_id"])
    if "transfer_id" in kwargs:
        resolved["transfer"] = TicketTransfer.objects.get(pk=kwargs["transfer_id"])
    if "host_profile_id" in kwargs:
        resolved["host_profile"] = HostProfile.objects.get(pk=kwargs["host_profile_id"])
    return resolved


@app.task(bind=True, max_retries=5, default_retry_delay=60)
def create_host_subaccounts_task(self, host_profile_id: str):
    try:
        from payments.tasks import create_host_subaccounts
        create_host_subaccounts(host_profile_id)
    except Exception as exc:
        raise self.retry(exc=exc)
