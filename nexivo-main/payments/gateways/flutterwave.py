"""
Flutterwave adapter. API docs: https://developer.flutterwave.com/
Split payment model: a transaction is initialized with a `subaccounts`
array specifying the host's subaccount and the exact transaction_split_ratio
or transaction_charge_amount that should be routed to them, with the
remainder settling to the platform's primary account.
"""

import hashlib
import hmac
from decimal import Decimal

import requests
from django.conf import settings

from payments.gateways.base import BaseGatewayClient, GatewayError

BASE_URL = "https://api.flutterwave.com/v3"


class FlutterwaveClient(BaseGatewayClient):
    name = "flutterwave"

    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"}

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(method, f"{BASE_URL}{path}", headers=self._headers(), timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise GatewayError(f"Flutterwave request failed: {exc}") from exc

        if response.status_code >= 400:
            raise GatewayError(f"Flutterwave error {response.status_code}: {response.text[:500]}")
        return response.json()

    def initialize_transaction(self, *, reference, amount, currency, email, callback_url, metadata, subaccount_id=None, host_amount=None):
        payload = {
            "tx_ref": reference,
            "amount": str(amount),
            "currency": currency,
            "redirect_url": callback_url,
            "customer": {"email": email},
            "meta": metadata,
        }
        if subaccount_id and host_amount is not None:
            payload["subaccounts"] = [
                {"id": subaccount_id, "transaction_charge_type": "flat", "transaction_charge": str(host_amount)}
            ]

        data = self._request("POST", "/payments", json=payload)
        result = data.get("data", {})
        return {"checkout_url": result.get("link"), "raw": data}

    def verify_transaction(self, *, reference):
        data = self._request("GET", "/transactions/verify_by_reference", params={"tx_ref": reference})
        result = data.get("data", {})
        gateway_status = result.get("status")
        status_map = {"successful": "success", "failed": "failed"}
        return {
            "status": status_map.get(gateway_status, "pending"),
            "amount": Decimal(str(result.get("amount", 0))),
            "currency": result.get("currency", "NGN"),
            "gateway_transaction_id": str(result.get("id", "")),
            "raw": data,
        }

    def create_subaccount(self, *, host_profile):
        payload = {
            "account_bank": host_profile.bank_code,
            "account_number": host_profile.account_number,
            "business_name": host_profile.business_name or host_profile.user.username,
            "business_email": host_profile.user.email,
            "split_type": "flat",
            "split_value": 0,
        }
        data = self._request("POST", "/subaccounts", json=payload)
        result = data.get("data", {})
        return {"subaccount_code": str(result.get("id", "")), "raw": data}

    def initiate_refund(self, *, gateway_transaction_id, amount):
        payload = {}
        if amount is not None:
            payload["amount"] = str(amount)
        data = self._request("POST", f"/transactions/{gateway_transaction_id}/refund", json=payload)
        result = data.get("data", {})
        return {
            "gateway_refund_id": str(result.get("id", "")),
            "status": result.get("status", "pending"),
            "raw": data,
        }

    def verify_webhook_signature(self, *, payload_body: bytes, headers: dict) -> bool:
        signature = headers.get("verif-hash") or headers.get("Verif-Hash")
        secret_hash = getattr(settings, "FLUTTERWAVE_WEBHOOK_SECRET_HASH", "") or self.secret_key
        if not signature:
            return False
        return hmac.compare_digest(signature, secret_hash)

    def list_transactions(self, *, from_date, to_date):
        data = self._request(
            "GET", "/transactions",
            params={"from": from_date.isoformat(), "to": to_date.isoformat(), "status": "successful"},
        )
        return data.get("data", [])
