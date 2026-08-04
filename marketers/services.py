"""
marketers/services.py
Call this after every successful payment to credit marketer commission.
"""
from decimal import Decimal
import logging

logger = logging.getLogger("nexivo")


def credit_marketer_commission(booking, nexivo_cut: Decimal):
    """
    Credits 10% of Nexivo's cut to the marketer who referred this event.
    Call this from payments/services.py after confirm_booking().
    """
    try:
        from marketers.models import Marketer, MarketerCommission

        event = booking.event
        referral_code = getattr(event, 'marketer_referral_code', None)
        if not referral_code:
            return  # No marketer attached to this event

        marketer = Marketer.objects.get(referral_code=referral_code, is_active=True)

        commission = nexivo_cut * Decimal('0.10')  # 10% of Nexivo's 5% cut
        commission = commission.quantize(Decimal('0.01'))

        MarketerCommission.objects.create(
            marketer=marketer,
            event=event,
            booking=booking,
            ticket_revenue=booking.total_amount,
            nexivo_cut=nexivo_cut,
            commission_amount=commission,
            status='credited',
        )

        marketer.wallet_balance += commission
        marketer.total_earned += commission
        marketer.save(update_fields=['wallet_balance', 'total_earned'])

        logger.info("Credited ₦%s commission to marketer %s", commission, marketer.referral_code)

    except Marketer.DoesNotExist:
        logger.warning("Marketer with referral code %s not found", referral_code)
    except Exception as e:
        logger.error("Failed to credit marketer commission: %s", e)