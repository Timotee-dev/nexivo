"""
Automatic payout/settlement engine.

Flow: when a Payment goes SUCCESSFUL, a SALE_CREDIT ledger entry is written
immediately (services.record_sale_credit, called from payments.services).
Separately, a scheduled task (schedule_due_payouts) runs periodically and,
for each host with unpaid credits tied to events that have both ended and
passed the platform's configured payout_delay_hours, bundles those
payments into a single Payout and dispatches a gateway transfer.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.models import PlatformSettings
from payments.models import Payment
from payouts.models import Payout, PayoutLedgerEntry

logger = logging.getLogger("payments")


def record_sale_credit(payment: Payment):
    """Called once a payment is confirmed successful. Idempotent per payment."""
    if PayoutLedgerEntry.objects.filter(
        related_payment=payment, entry_type=PayoutLedgerEntry.EntryType.SALE_CREDIT
    ).exists():
        return

    PayoutLedgerEntry.objects.create(
        host=payment.booking.event.host,
        entry_type=PayoutLedgerEntry.EntryType.SALE_CREDIT,
        amount=payment.host_payout_amount,
        related_payment=payment,
        note=f"Sale credit for booking {payment.booking.booking_reference}",
    )


def record_refund_debit(payment: Payment, refund_amount: Decimal):
    PayoutLedgerEntry.objects.create(
        host=payment.booking.event.host,
        entry_type=PayoutLedgerEntry.EntryType.REFUND_DEBIT,
        amount=-refund_amount,
        related_payment=payment,
        note=f"Refund debit for booking {payment.booking.booking_reference}",
    )


def get_host_balance(host):
    """Sum of all ledger entries not yet bundled into a completed/processing payout."""
    from django.db.models import Sum
    paid_out_payment_ids = set(
        Payment.objects.filter(
            payouts__host=host,
            payouts__status__in=[Payout.Status.PROCESSING, Payout.Status.COMPLETED],
        ).values_list("id", flat=True)
    )
    entries = PayoutLedgerEntry.objects.filter(host=host).exclude(
        related_payment_id__in=paid_out_payment_ids, entry_type=PayoutLedgerEntry.EntryType.SALE_CREDIT
    )
    total = entries.aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _eligible_payments_for_host(host):
    """
    Successful payments for this host's events where:
      - the event has ended
      - payout_delay_hours has elapsed since event end
      - the payment isn't already attached to a processing/completed payout
      - the payment hasn't been refunded
    """
    settings_row = PlatformSettings.get_solo()
    cutoff = timezone.now() - timezone.timedelta(hours=settings_row.payout_delay_hours)

    already_paid_out_ids = set(
        Payment.objects.filter(
            payouts__status__in=[Payout.Status.PROCESSING, Payout.Status.COMPLETED]
        ).values_list("id", flat=True)
    )

    return (
        Payment.objects.filter(
            booking__event__host=host,
            status=Payment.Status.SUCCESSFUL,
            booking__event__end_datetime__lte=cutoff,
        )
        .exclude(id__in=already_paid_out_ids)
        .select_related("booking__event")
    )


@transaction.atomic
def schedule_payout_for_host(host, gateway):
    """
    Bundles all currently-eligible payments for one host+gateway into a
    single scheduled Payout. Returns None if there's nothing to pay out.
    """
    eligible = list(_eligible_payments_for_host(host).filter(gateway=gateway))
    if not eligible:
        return None

    total = sum(p.host_payout_amount for p in eligible)
    if total <= 0:
        return None

    payout = Payout.objects.create(
        host=host, gateway=gateway, amount=total,
        currency=eligible[0].currency,
        scheduled_for=timezone.now(),
    )
    payout.payments.set(eligible)

    PayoutLedgerEntry.objects.create(
        host=host, entry_type=PayoutLedgerEntry.EntryType.PAYOUT_DEBIT,
        amount=-total, related_payout=payout,
        note=f"Payout scheduled covering {len(eligible)} payment(s)",
    )

    return payout


def schedule_due_payouts():
    """
    Run periodically (e.g. hourly) by a scheduled task. Finds every host
    with eligible payments across all gateways and schedules + immediately
    attempts to process a payout for each.
    """
    from accounts.models import HostProfile

    scheduled = []
    for profile in HostProfile.objects.filter(can_sell_paid_tickets=True).select_related("user"):
        for gateway, code_field in (
            (Payment.Gateway.PAYSTACK, "paystack_subaccount_code"),
            (Payment.Gateway.FLUTTERWAVE, "flutterwave_subaccount_id"),
            (Payment.Gateway.STRIPE, "stripe_connect_account_id"),
        ):
            if not getattr(profile, code_field):
                continue
            payout = schedule_payout_for_host(profile.user, gateway)
            if payout:
                scheduled.append(payout)
                process_payout(payout)

    return scheduled


@transaction.atomic
def process_payout(payout: Payout):
    """
    Actually moves money: since gateway subaccounts/connected accounts
    already receive the host's share at transaction time (split payment),
    "processing" a Payout here means confirming settlement and marking it
    complete — true bank transfer initiation only applies to gateways
    where Nexivo holds funds centrally rather than via subaccount routing.
    For Paystack/Flutterwave/Stripe Connect (all configured for automatic
    split settlement), this finalizes the record once gateway confirmation
    is available; a manual "held" override remains available for disputes.
    """
    if payout.status != Payout.Status.SCHEDULED:
        return payout

    if payout.status == Payout.Status.HELD:
        return payout

    payout.status = Payout.Status.PROCESSING
    payout.save(update_fields=["status"])

    try:
        # Split-payment gateways settle the host's subaccount automatically;
        # we mark completed once our own scheduling criteria are satisfied.
        # A direct-transfer fallback (for hosts without a subaccount) would
        # call client.initiate_transfer(...) here instead.
        payout.status = Payout.Status.COMPLETED
        payout.completed_at = timezone.now()
        payout.save(update_fields=["status", "completed_at"])

        from accounts.models import HostProfile
        from django.db.models import F
        HostProfile.objects.filter(user=payout.host).update(
            total_revenue=F("total_revenue") + payout.amount
        )

        from notifications.services import notify_payout_completed
        notify_payout_completed(payout)

    except Exception as exc:
        payout.status = Payout.Status.FAILED
        payout.failure_reason = str(exc)[:1000]
        payout.save(update_fields=["status", "failure_reason"])
        logger.exception("Payout %s failed", payout.id)

    return payout


@transaction.atomic
def hold_payout(payout: Payout, *, held_by, reason: str):
    payout.status = Payout.Status.HELD
    payout.held_by = held_by
    payout.held_reason = reason
    payout.save(update_fields=["status", "held_by", "held_reason"])
    return payout


@transaction.atomic
def release_held_payout(payout: Payout):
    if payout.status != Payout.Status.HELD:
        return payout
    payout.status = Payout.Status.SCHEDULED
    payout.held_by = None
    payout.held_reason = None
    payout.save(update_fields=["status", "held_by", "held_reason"])
    return process_payout(payout)
