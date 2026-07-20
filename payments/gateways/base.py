"""
Common interface every gateway adapter implements, so the rest of the
payments app (services.py, views.py, webhook handlers) never branches on
gateway type beyond picking the right adapter instance.
"""

from abc import ABC, abstractmethod


class GatewayError(Exception):
    """Raised on any unrecoverable gateway API error (network, 4xx/5xx, bad response shape)."""


class BaseGatewayClient(ABC):
    name: str

    @abstractmethod
    def initialize_transaction(self, *, reference, amount, currency, email, callback_url, metadata):
        """
        Starts a hosted-checkout transaction. Returns dict with at least
        {"checkout_url": str, "raw": dict}.
        """

    @abstractmethod
    def verify_transaction(self, *, reference):
        """
        Confirms a transaction's final status with the gateway (the only
        source of truth — webhooks are a notification, not proof).
        Returns dict: {"status": "success"|"failed"|"pending", "amount": Decimal,
        "currency": str, "gateway_transaction_id": str, "raw": dict}.
        """

    @abstractmethod
    def create_subaccount(self, *, host_profile):
        """
        Creates a payout subaccount for a host using their submitted bank
        details. Returns dict: {"subaccount_code": str, "raw": dict}.
        """

    @abstractmethod
    def initiate_refund(self, *, gateway_transaction_id, amount):
        """Returns dict: {"gateway_refund_id": str, "status": str, "raw": dict}."""

    @abstractmethod
    def verify_webhook_signature(self, *, payload_body: bytes, headers: dict) -> bool:
        """Returns True iff the inbound webhook's signature is authentic."""

    @abstractmethod
    def list_transactions(self, *, from_date, to_date):
        """Returns a list of gateway-side transactions for reconciliation."""
