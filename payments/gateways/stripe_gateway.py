"""
Stripe adapter, used primarily for international cards. Split payment via
Stripe Connect: a Checkout Session is created with `payment_intent_data.
application_fee_amount` (our commission) and `transfer_data.destination`
(the host's connected account), so Stripe auto-splits the settlement —
the host's connected account receives the ticket revenue minus our fee,
and our platform account receives the fee directly.
"""

from decimal import Decimal

import stripe
from django.conf import settings

from payments.gateways.base import BaseGatewayClient, GatewayError


class StripeClient(BaseGatewayClient):
    name = "stripe"

    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    def initialize_transaction(self, *, reference, amount, currency, email, callback_url, metadata, connected_account_id=None, commission_amount=None):
        amount_minor = int((Decimal(amount) * 100).to_integral_value())
        try:
            session_kwargs = {
                "mode": "payment",
                "payment_method_types": ["card"],
                "customer_email": email,
                "client_reference_id": reference,
                "metadata": metadata,
                "line_items": [{
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_minor,
                        "product_data": {"name": f"Nexivo booking {reference}"},
                    },
                    "quantity": 1,
                }],
                "success_url": f"{callback_url}?status=success&reference={reference}",
                "cancel_url": f"{callback_url}?status=cancelled&reference={reference}",
            }
            if connected_account_id and commission_amount is not None:
                session_kwargs["payment_intent_data"] = {
                    "application_fee_amount": int((Decimal(commission_amount) * 100).to_integral_value()),
                    "transfer_data": {"destination": connected_account_id},
                }
            session = stripe.checkout.Session.create(**session_kwargs)
        except stripe.error.StripeError as exc:
            raise GatewayError(f"Stripe error: {exc}") from exc

        return {"checkout_url": session.url, "raw": session}

    def verify_transaction(self, *, reference):
        try:
            sessions = stripe.checkout.Session.list(limit=1)
            # In production, store the session ID at initialization time rather
            # than searching; kept here for interface completeness.
            matched = None
            for session in stripe.checkout.Session.list(limit=100).auto_paging_iter():
                if session.client_reference_id == reference:
                    matched = session
                    break
        except stripe.error.StripeError as exc:
            raise GatewayError(f"Stripe verify failed: {exc}") from exc

        if not matched:
            return {"status": "pending", "amount": Decimal("0"), "currency": "usd", "gateway_transaction_id": "", "raw": {}}

        status_map = {"complete": "success", "expired": "failed", "open": "pending"}
        return {
            "status": status_map.get(matched.status, "pending"),
            "amount": Decimal(matched.amount_total or 0) / 100,
            "currency": matched.currency,
            "gateway_transaction_id": matched.payment_intent or matched.id,
            "raw": matched,
        }

    def create_subaccount(self, *, host_profile):
        try:
            account = stripe.Account.create(
                type="express",
                country="NG",
                email=host_profile.user.email,
                capabilities={"transfers": {"requested": True}, "card_payments": {"requested": True}},
            )
        except stripe.error.StripeError as exc:
            raise GatewayError(f"Stripe Connect account creation failed: {exc}") from exc
        return {"subaccount_code": account.id, "raw": account}

    def initiate_refund(self, *, gateway_transaction_id, amount):
        try:
            kwargs = {"payment_intent": gateway_transaction_id}
            if amount is not None:
                kwargs["amount"] = int((Decimal(amount) * 100).to_integral_value())
            refund = stripe.Refund.create(**kwargs)
        except stripe.error.StripeError as exc:
            raise GatewayError(f"Stripe refund failed: {exc}") from exc
        return {"gateway_refund_id": refund.id, "status": refund.status, "raw": refund}

    def verify_webhook_signature(self, *, payload_body: bytes, headers: dict) -> bool:
        signature = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        if not signature:
            return False
        try:
            stripe.Webhook.construct_event(payload_body, signature, self.webhook_secret)
            return True
        except (stripe.error.SignatureVerificationError, ValueError):
            return False

    def list_transactions(self, *, from_date, to_date):
        import time
        try:
            charges = stripe.Charge.list(
                created={"gte": int(time.mktime(from_date.timetuple())), "lte": int(time.mktime(to_date.timetuple()))},
                limit=100,
            )
        except stripe.error.StripeError as exc:
            raise GatewayError(f"Stripe list_transactions failed: {exc}") from exc
        return charges.data
