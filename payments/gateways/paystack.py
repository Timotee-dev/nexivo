"""
Paystack adapter. API docs: https://paystack.com/docs/api/
Uses the split-payment-via-subaccount model: a transaction is initialized
with a `subaccount` and `transaction_charge` (our commission, in kobo),
so Paystack settles the host's share to their subaccount and our share to
the platform's main account automatically — no manual transfer step needed.
"""

import hashlib
import hmac
from decimal import Decimal

import requests
from django.conf import settings

from payments.gateways.base import BaseGatewayClient, GatewayError

BASE_URL = "https://api.paystack.co"


class PaystackClient(BaseGatewayClient):
    name = "paystack"

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"}

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(method, f"{BASE_URL}{path}", headers=self._headers(), timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise GatewayError(f"Paystack request failed: {exc}") from exc

        if response.status_code >= 400:
            raise GatewayError(f"Paystack error {response.status_code}: {response.text[:500]}")
        return response.json()

    def initialize_transaction(self, *, reference, amount, currency, email, callback_url, metadata, subaccount_code=None, commission_amount=None):
        amount_kobo = int((Decimal(amount) * 100).to_integral_value())
        payload = {
            "reference": reference,
            "amount": amount_kobo,
            "currency": currency,
            "email": email,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        if subaccount_code:
            payload["subaccount"] = subaccount_code
            if commission_amount is not None:
                payload["transaction_charge"] = int((Decimal(commission_amount) * 100).to_integral_value())
                payload["bearer"] = "subaccount"

        data = self._request("POST", "/transaction/initialize", json=payload)
        result = data.get("data", {})
        return {"checkout_url": result.get("authorization_url"), "raw": data}

    def verify_transaction(self, *, reference):
        data = self._request("GET", f"/transaction/verify/{reference}")
        result = data.get("data", {})
        gateway_status = result.get("status")
        status_map = {"success": "success", "failed": "failed", "abandoned": "abandoned"}
        return {
            "status": status_map.get(gateway_status, "pending"),
            "amount": Decimal(result.get("amount", 0)) / 100,
            "currency": result.get("currency", "NGN"),
            "gateway_transaction_id": str(result.get("id", "")),
            "raw": data,
        }

    def create_subaccount(self, *, host_profile):
        payload = {
            "business_name": host_profile.business_name or host_profile.user.username,
            "settlement_bank": host_profile.bank_code,
            "account_number": host_profile.account_number,
            "percentage_charge": 0,  # we control the split per-transaction via transaction_charge instead
        }
        data = self._request("POST", "/subaccount", json=payload)
        result = data.get("data", {})
        return {"subaccount_code": result.get("subaccount_code"), "raw": data}

    def initiate_refund(self, *, gateway_transaction_id, amount):
        payload = {"transaction": gateway_transaction_id}
        if amount is not None:
            payload["amount"] = int((Decimal(amount) * 100).to_integral_value())
        data = self._request("POST", "/refund", json=payload)
        result = data.get("data", {})
        return {"gateway_refund_id": str(result.get("id", "")), "status": result.get("status", "pending"), "raw": data}

    def verify_webhook_signature(self, *, payload_body: bytes, headers: dict) -> bool:
        signature = headers.get("x-paystack-signature") or headers.get("X-Paystack-Signature")
        if not signature:
            return False
        computed = hmac.new(self.secret_key.encode(), payload_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed, signature)

    def list_transactions(self, *, from_date, to_date):
        data = self._request(
            "GET", "/transaction",
            params={"from": from_date.isoformat(), "to": to_date.isoformat(), "perPage": 100, "status": "success"},
        )
        return data.get("data", [])
