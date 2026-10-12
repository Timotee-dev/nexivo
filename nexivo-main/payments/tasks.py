"""
Background task entry points for the payments app.
"""

import logging
from django.conf import settings

logger = logging.getLogger("nexivo")


def create_host_subaccounts(host_profile_id):
    """
    Creates Paystack subaccount for a host who has just submitted bank details.
    Flutterwave and Stripe are skipped if their keys are not configured.
    """
    from accounts.models import HostProfile
    from payments.gateways.base import GatewayError
    from payments.models import Payment

    try:
        profile = HostProfile.objects.get(pk=host_profile_id)
    except HostProfile.DoesNotExist:
        logger.error("create_host_subaccounts: HostProfile %s not found", host_profile_id)
        return

    if not profile.bank_code or not profile.account_number:
        logger.warning("create_host_subaccounts: profile %s missing bank details", host_profile_id)
        return

    any_succeeded = False

    # Only try Paystack if key is configured
    paystack_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if paystack_key:
        try:
            from payments.gateways.paystack import PaystackClient
            client = PaystackClient()
            result = client.create_subaccount(host_profile=profile)
            subaccount_code = result.get("subaccount_code")
            if subaccount_code:
                profile.paystack_subaccount_code = subaccount_code
                any_succeeded = True
                logger.info("Created Paystack subaccount for host_profile=%s: %s", host_profile_id, subaccount_code)
            else:
                logger.error("Paystack subaccount creation returned no code: %s", result)
        except GatewayError as exc:
            logger.error("Failed to create Paystack subaccount for host_profile=%s: %s", host_profile_id, exc)
        except Exception:
            logger.exception("Unexpected error creating Paystack subaccount for host_profile=%s", host_profile_id)
    else:
        logger.warning("PAYSTACK_SECRET_KEY not set — skipping Paystack subaccount creation")

    # Skip Flutterwave if key not configured
    flutterwave_key = getattr(settings, 'FLUTTERWAVE_SECRET_KEY', '')
    if flutterwave_key:
        try:
            from payments.gateways.flutterwave import FlutterwaveClient
            client = FlutterwaveClient()
            result = client.create_subaccount(host_profile=profile)
            subaccount_code = result.get("subaccount_code")
            if subaccount_code:
                profile.flutterwave_subaccount_id = subaccount_code
                any_succeeded = True
        except Exception as exc:
            logger.error("Failed to create Flutterwave subaccount: %s", exc)

    # Skip Stripe if key not configured
    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if stripe_key:
        try:
            from payments.gateways.stripe_gw import StripeClient
            client = StripeClient()
            result = client.create_subaccount(host_profile=profile)
            subaccount_code = result.get("subaccount_code")
            if subaccount_code:
                profile.stripe_connect_account_id = subaccount_code
                any_succeeded = True
        except Exception as exc:
            logger.error("Failed to create Stripe subaccount: %s", exc)

    if any_succeeded:
        profile.bank_details_verified = True
        profile.refresh_paid_ticket_eligibility()

    profile.save(update_fields=[
        "paystack_subaccount_code", "flutterwave_subaccount_id",
        "stripe_connect_account_id", "bank_details_verified", "can_sell_paid_tickets",
    ])