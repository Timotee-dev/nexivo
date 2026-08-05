"""
Core payment orchestration: initialization, verification, webhook processing,
refunds, and a lightweight fraud-scoring pass. All money-moving operations
are wrapped in transactions and are written to be safe under webhook retries
(idempotent) since gateways routinely redeliver the same notification.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking
from bookings.services import cancel_booking, confirm_booking
from core.models import PlatformSettings
from payments.gateways.registry import get_gateway_client
from payments.models import Payment, Refund, WebhookEvent

logger = logging.getLogger("payments")


def _split_amounts(total_amount: Decimal, commission_percent):
    commission_percent = Decimal(str(commission_percent))
    commission_amount = (total_amount * commission_percent / Decimal("100")).quantize(Decimal("0.01"))
    host_amount = total_amount - commission_amount
    return commission_amount, host_amount


def score_fraud_risk(*, booking, ip_address=None):
    """
    Lightweight heuristic fraud scorer (0-100). Not a replacement for a real
    fraud ML model, but catches obvious abuse patterns cheaply:
    rapid repeat bookings, mismatched email/IP velocity, unusually large orders.
    Flags for manual review above the threshold rather than blocking outright,
    since false positives on a live ticketing checkout are costly.
    """
    score = 0
    reasons = []

    recent_count = Booking.objects.filter(
        customer=booking.customer,
        created_at__gte=timezone.now() - timezone.timedelta(minutes=10),
    ).count()
    if recent_count >= 5:
        score += 40
        reasons.append("5+ bookings by this customer in 10 minutes")

    if booking.total_amount > Decimal("500000"):
        score += 25
        reasons.append("unusually large order amount")

    if booking.ticket_count > 20:
        score += 20
        reasons.append("unusually large ticket quantity in one order")

    if ip_address:
        ip_recent_count = Payment.objects.filter(
            ip_address=ip_address, created_at__gte=timezone.now() - timezone.timedelta(minutes=10)
        ).count()
        if ip_recent_count >= 8:
            score += 30
            reasons.append("high payment velocity from this IP")

    return min(score, 100), reasons


@transaction.atomic
def initialize_payment(*, booking, gateway, ip_address=None):
    """
    Computes the commission/host split using the *current* platform rate,
    snapshots it onto the Payment, runs a fraud check, and asks the chosen
    gateway to start a hosted checkout session.
    """
    settings_row = PlatformSettings.get_solo()
    commission_amount, host_amount = _split_amounts(
        booking.total_amount, settings_row.platform_commission_percent
    )

    payment = Payment.objects.create(
        booking=booking,
        customer=booking.customer,
        gateway=gateway,
        gateway_reference=booking.booking_reference,
        amount=booking.total_amount,
        currency=booking.currency,
        platform_commission_percent=settings_row.platform_commission_percent,
        platform_commission_amount=commission_amount,
        host_payout_amount=host_amount,
        ip_address=ip_address,
    )

    risk_score, risk_reasons = score_fraud_risk(booking=booking, ip_address=ip_address)
    payment.risk_score = risk_score
    payment.flagged_for_review = risk_score >= 60
    payment.save(update_fields=["risk_score", "flagged_for_review"])
    if payment.flagged_for_review:
        logger.warning("Payment %s flagged for review (score=%s): %s", payment.id, risk_score, risk_reasons)

    host_profile = getattr(booking.event.host, "host_profile", None)
    client = get_gateway_client(gateway)
    callback_url = f"{settings.FRONTEND_URL}/checkout/callback"

    init_kwargs = dict(
        reference=payment.gateway_reference,
        amount=booking.total_amount,
        currency=booking.currency,
        email=booking.customer_email,
        callback_url=callback_url,
        metadata={"booking_id": str(booking.id), "payment_id": str(payment.id)},
    )

    if gateway == Payment.Gateway.PAYSTACK and host_profile and host_profile.paystack_subaccount_code:
        init_kwargs["subaccount_code"] = host_profile.paystack_subaccount_code
        init_kwargs["commission_amount"] = commission_amount
    elif gateway == Payment.Gateway.FLUTTERWAVE and host_profile and host_profile.flutterwave_subaccount_id:
        init_kwargs["subaccount_id"] = host_profile.flutterwave_subaccount_id
        init_kwargs["host_amount"] = host_amount
    elif gateway == Payment.Gateway.STRIPE and host_profile and host_profile.stripe_connect_account_id:
        init_kwargs["connected_account_id"] = host_profile.stripe_connect_account_id
        init_kwargs["commission_amount"] = commission_amount

    result = client.initialize_transaction(**init_kwargs)

    payment.checkout_url = result.get("checkout_url")
    payment.authorization_data = {"init_response_summary": str(result.get("raw"))[:2000]}
    payment.status = Payment.Status.PENDING
    payment.save(update_fields=["checkout_url", "authorization_data", "status"])

    return {
        "payment_id": str(payment.id),
        "gateway": gateway,
        "checkout_url": payment.checkout_url,
        "reference": payment.gateway_reference,
    }


@transaction.atomic
def verify_and_finalize_payment(payment: Payment):
    """
    Calls the gateway's verify endpoint (source of truth) and finalizes the
    payment + booking accordingly. Idempotent: re-verifying an already
    SUCCESSFUL payment is a no-op.
    """
    if payment.status == Payment.Status.SUCCESSFUL:
        return payment

    client = get_gateway_client(payment.gateway)
    result = client.verify_transaction(reference=payment.gateway_reference)

    if result["status"] == "success":
        if result["amount"] and abs(result["amount"] - payment.amount) > Decimal("0.01"):
            payment.status = Payment.Status.DISPUTED
            payment.failed_reason = (
                f"Amount mismatch: gateway reports {result['amount']} {result['currency']}, "
                f"expected {payment.amount} {payment.currency}."
            )
            payment.save(update_fields=["status", "failed_reason"])
            logger.error("Payment %s amount mismatch on verify: %s", payment.id, payment.failed_reason)
            return payment

        payment.status = Payment.Status.SUCCESSFUL
        payment.gateway_transaction_id = result["gateway_transaction_id"]
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "gateway_transaction_id", "paid_at"])

        confirm_booking(payment.booking)

        from payments.invoice_generation import generate_invoice_pdf
        invoice_file = generate_invoice_pdf(payment)
        payment.invoice_pdf.save(invoice_file.name, invoice_file, save=True)

        from payouts.services import record_sale_credit
        record_sale_credit(payment)

        from notifications.services import notify_payment_successful
        notify_payment_successful(payment)

    elif result["status"] == "failed":
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        cancel_booking(payment.booking, reason="Payment failed.")

        from notifications.services import notify_payment_failed
        notify_payment_failed(payment.booking)

    # "pending"/"abandoned" -> leave as-is; caller (webhook or polling) will retry later.
    return payment


@transaction.atomic
def process_webhook(*, gateway, payload, headers, raw_body):
    """
    Records every inbound webhook (verified or not) for audit, deduplicates
    by (gateway, event_id), verifies the signature, and on success re-runs
    verify_and_finalize_payment() against the gateway's API directly rather
    than trusting webhook payload fields — the webhook is just a trigger to
    check, never the source of truth for money movement.
    """
    event_id = _extract_event_id(gateway, payload)
    event_type = _extract_event_type(gateway, payload)

    if event_id:
        existing = WebhookEvent.objects.filter(gateway=gateway, event_id=event_id).first()
        if existing:
            existing.retry_count += 1
            existing.save(update_fields=["retry_count"])
            return {"status": "duplicate_ignored", "webhook_event_id": str(existing.id)}

    webhook_event = WebhookEvent.objects.create(
        gateway=gateway, event_type=event_type, event_id=event_id,
        payload=payload, headers={k: v for k, v in headers.items() if k.lower() not in ("authorization",)},
    )

    client = get_gateway_client(gateway)
    if not client.verify_webhook_signature(payload_body=raw_body, headers=headers):
        webhook_event.status = WebhookEvent.ProcessingStatus.REJECTED
        webhook_event.save(update_fields=["status"])
        logger.warning("Rejected webhook with invalid signature from %s", gateway)
        return {"status": "rejected", "webhook_event_id": str(webhook_event.id)}

    webhook_event.status = WebhookEvent.ProcessingStatus.VERIFIED
    webhook_event.save(update_fields=["status"])

    reference = _extract_reference(gateway, payload)
    if not reference:
        webhook_event.status = WebhookEvent.ProcessingStatus.FAILED
        webhook_event.last_error = "Could not extract a payment reference from webhook payload."
        webhook_event.save(update_fields=["status", "last_error"])
        return {"status": "failed", "webhook_event_id": str(webhook_event.id)}

    try:
        payment = Payment.objects.select_for_update().get(gateway_reference=reference, gateway=gateway)
    except Payment.DoesNotExist:
        webhook_event.status = WebhookEvent.ProcessingStatus.FAILED
        webhook_event.last_error = f"No local payment found for reference {reference}."
        webhook_event.save(update_fields=["status", "last_error"])
        return {"status": "failed", "webhook_event_id": str(webhook_event.id)}

    try:
        verify_and_finalize_payment(payment)
        webhook_event.status = WebhookEvent.ProcessingStatus.PROCESSED
        webhook_event.related_payment = payment
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "related_payment", "processed_at"])
    except Exception as exc:
        webhook_event.status = WebhookEvent.ProcessingStatus.FAILED
        webhook_event.last_error = str(exc)[:2000]
        webhook_event.save(update_fields=["status", "last_error"])
        logger.exception("Webhook processing failed for payment %s", payment.id)
        return {"status": "failed", "webhook_event_id": str(webhook_event.id)}

    return {"status": "processed", "webhook_event_id": str(webhook_event.id), "payment_status": payment.status}


def _extract_event_id(gateway, payload):
    if gateway == Payment.Gateway.PAYSTACK:
        return str(payload.get("data", {}).get("id", "")) or None
    if gateway == Payment.Gateway.FLUTTERWAVE:
        return str(payload.get("data", {}).get("id", "")) or None
    if gateway == Payment.Gateway.STRIPE:
        return payload.get("id")
    return None


def _extract_event_type(gateway, payload):
    if gateway in (Payment.Gateway.PAYSTACK, Payment.Gateway.FLUTTERWAVE):
        return payload.get("event") or payload.get("event.type")
    if gateway == Payment.Gateway.STRIPE:
        return payload.get("type")
    return None


def _extract_reference(gateway, payload):
    data = payload.get("data", {})
    if gateway == Payment.Gateway.PAYSTACK:
        return data.get("reference")
    if gateway == Payment.Gateway.FLUTTERWAVE:
        return data.get("tx_ref")
    if gateway == Payment.Gateway.STRIPE:
        obj = payload.get("data", {}).get("object", {})
        return obj.get("client_reference_id")
    return None


@transaction.atomic
def request_refund(*, payment: Payment, requested_by, amount=None, reason=""):
    settings_row = PlatformSettings.get_solo()
    refund_amount = amount if amount is not None else payment.amount
    fee_percent = Decimal(str(settings_row.refund_processing_fee_percent))
    fee = (refund_amount * fee_percent / Decimal("100")).quantize(Decimal("0.01"))

    refund = Refund.objects.create(
        payment=payment, requested_by=requested_by, amount=refund_amount,
        processing_fee_deducted=fee, reason=reason,
    )
    return refund


@transaction.atomic
def approve_refund(*, refund: Refund, approved_by):
    if refund.status != Refund.Status.REQUESTED:
        return refund

    client = get_gateway_client(refund.payment.gateway)
    try:
        result = client.initiate_refund(
            gateway_transaction_id=refund.payment.gateway_transaction_id,
            amount=refund.amount,
        )
    except Exception as exc:
        refund.status = Refund.Status.FAILED
        refund.rejection_reason = str(exc)[:1000]
        refund.save(update_fields=["status", "rejection_reason"])
        raise

    refund.status = Refund.Status.PROCESSING
    refund.approved_by = approved_by
    refund.gateway_refund_id = result.get("gateway_refund_id", "")
    refund.save(update_fields=["status", "approved_by", "gateway_refund_id"])

    payment = refund.payment
    total_refunded = sum(
        r.amount for r in payment.refunds.filter(status__in=[Refund.Status.PROCESSING, Refund.Status.COMPLETED])
    )
    payment.status = (
        Payment.Status.REFUNDED if total_refunded >= payment.amount else Payment.Status.PARTIALLY_REFUNDED
    )
    payment.save(update_fields=["status"])

    booking = payment.booking
    booking.status = (
        Booking.Status.REFUNDED if total_refunded >= payment.amount else Booking.Status.PARTIALLY_REFUNDED
    )
    booking.save(update_fields=["status"])

    from payouts.services import record_refund_debit
    record_refund_debit(payment, refund.amount)

    from notifications.services import notify_refund_update
    notify_refund_update(refund)

    return refund
