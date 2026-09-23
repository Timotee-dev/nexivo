"""
affiliates/services.py
Call credit_affiliate_commission() from bookings/services.py after confirm_booking
"""
from decimal import Decimal
import logging

logger = logging.getLogger("nexivo")


def credit_affiliate_commission(booking, affiliate_code: str):
    """
    Credits commission to the event affiliate who referred this booking.
    Commission comes from the HOST's cut — not from Nexivo's cut.
    """
    try:
        from affiliates.models import EventAffiliate, AffiliateCommission

        affiliate = EventAffiliate.objects.get(
            referral_code=affiliate_code,
            event=booking.event,
            is_active=True,
        )

        # Commission is % of ticket revenue (from host's cut)
        commission = booking.total_amount * (affiliate.commission_rate / Decimal('100'))
        commission = commission.quantize(Decimal('0.01'))

        AffiliateCommission.objects.create(
            affiliate=affiliate,
            booking=booking,
            ticket_revenue=booking.total_amount,
            commission_amount=commission,
            status='credited',
        )

        affiliate.wallet_balance += commission
        affiliate.total_earned += commission
        affiliate.save(update_fields=['wallet_balance', 'total_earned'])

        logger.info(
            "Credited ₦%s affiliate commission to %s for event %s",
            commission, affiliate.affiliate_name or affiliate.affiliate_email, booking.event.title
        )

    except EventAffiliate.DoesNotExist:
        logger.warning("Affiliate with code %s not found for event %s", affiliate_code, booking.event_id)
    except Exception as e:
        logger.error("Failed to credit affiliate commission: %s", e)


def get_affiliate_from_request(request, event):
    """
    Checks if the request has an affiliate referral code in session or cookies.
    Returns the affiliate code string or None.
    """
    # Check session first
    code = request.session.get(f'aff_{event.slug}')
    if code:
        return code
    # Check query param (for direct links)
    return request.GET.get('ref')