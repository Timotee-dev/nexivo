"""
Paystack API helper functions for split payments.
Handles subaccount creation and transaction initialization with splits.
"""
import json
import urllib.request
import urllib.error
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _paystack_request(method, path, data=None):
    """Make a request to the Paystack API."""
    secret = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret:
        return False, 'No Paystack secret key configured.'

    url = f'https://api.paystack.co{path}'
    headers = {
        'Authorization': f'Bearer {secret}',
        'Content-Type': 'application/json',
    }

    body = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read())
            msg = err_body.get('message', f'HTTP {e.code}')
        except Exception:
            msg = f'HTTP {e.code}'
        logger.error('Paystack API error (%s %s): %s', method, path, msg)
        return False, msg
    except urllib.error.URLError as e:
        logger.error('Paystack network error: %s', e.reason)
        return False, f'Network error: {e.reason}'
    except Exception as e:
        logger.exception('Unexpected Paystack error')
        return False, str(e)

    if not result.get('status'):
        return False, result.get('message', 'Request failed')

    return True, result.get('data', {})


def get_bank_list():
    """Fetch list of Nigerian banks with their Paystack codes."""
    ok, data = _paystack_request('GET', '/bank?country=nigeria')
    if ok:
        return data
    return []


def resolve_account(account_number, bank_code):
    """Verify an account number against a bank code. Returns (ok, account_name or error)."""
    ok, data = _paystack_request(
        'GET', f'/bank/resolve?account_number={account_number}&bank_code={bank_code}'
    )
    if ok:
        return True, data.get('account_name', '')
    return False, data  # data is error message string here


def create_subaccount(business_name, bank_code, account_number, percentage_charge):
    """
    Create a Paystack subaccount for a provider.
    percentage_charge = the PLATFORM's cut (e.g. 10 for 10%).
    Returns (ok, subaccount_code or error message).
    """
    payload = {
        'business_name': business_name,
        'settlement_bank': bank_code,
        'account_number': account_number,
        'percentage_charge': percentage_charge,
    }
    ok, data = _paystack_request('POST', '/subaccount', payload)
    if ok:
        return True, data.get('subaccount_code', '')
    return False, data


def initialize_transaction(email, amount_kobo, reference, subaccount_code, platform_percentage, callback_url=None):
    """
    Initialize a Paystack transaction with a split.
    The provider's subaccount gets (100 - platform_percentage)%,
    the main account keeps platform_percentage%.

    Returns (ok, dict with 'authorization_url' and 'access_code' or error message).
    """
    payload = {
        'email': email,
        'amount': amount_kobo,
        'reference': reference,
        'subaccount': subaccount_code,
        'transaction_charge': 0,  # let percentage_charge on subaccount handle the split
        'bearer': 'subaccount',
    }
    if callback_url:
        payload['callback_url'] = callback_url

    ok, data = _paystack_request('POST', '/transaction/initialize', payload)
    if ok:
        return True, data
    return False, data


def verify_transaction(reference):
    """Verify a transaction by reference. Returns (ok, data or error message)."""
    ok, data = _paystack_request('GET', f'/transaction/verify/{reference}')
    if ok:
        if data.get('status') == 'success':
            return True, data
        return False, f"Payment status: {data.get('status', 'unknown')}"
    return False, data
