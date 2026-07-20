"""
Background task entry points for the payments app. Calls here are
synchronous in this codebase; wire to Celery/RQ in production for true
async execution without blocking the request that triggered them.
"""

import logging

logger = logging.getLogger("nexivo")


def create_host_subaccounts(host_profile_id):
    """
    Creates payout subaccounts with all three gateways for a host who has
    just submitted bank details. Each gateway's subaccount ID is stored on
    the HostProfile so future payment initializations can route splits there.
    """
    from accounts.models import HostProfile
    from payments.gateways.base import GatewayError
    from payments.gateways.registry import get_gateway_client
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

    for gateway in (Payment.Gateway.PAYSTACK, Payment.Gateway.FLUTTERWAVE, Payment.Gateway.STRIPE):
        try:
            client = get_gateway_client(gateway)
            result = client.create_subaccount(host_profile=profile)
            subaccount_code = result["subaccount_code"]

            if gateway == Payment.Gateway.PAYSTACK:
                profile.paystack_subaccount_code = subaccount_code
            elif gateway == Payment.Gateway.FLUTTERWAVE:
                profile.flutterwave_subaccount_id = subaccount_code
            elif gateway == Payment.Gateway.STRIPE:
                profile.stripe_connect_account_id = subaccount_code

            any_succeeded = True
            logger.info("Created %s subaccount for host_profile=%s: %s", gateway, host_profile_id, subaccount_code)
        except GatewayError as exc:
            logger.error("Failed to create %s subaccount for host_profile=%s: %s", gateway, host_profile_id, exc)
        except Exception:
            logger.exception("Unexpected error creating %s subaccount for host_profile=%s", gateway, host_profile_id)

    if any_succeeded:
        profile.bank_details_verified = True
        profile.refresh_paid_ticket_eligibility()

    profile.save(update_fields=[
        "paystack_subaccount_code", "flutterwave_subaccount_id",
        "stripe_connect_account_id", "bank_details_verified", "can_sell_paid_tickets",
    ])
