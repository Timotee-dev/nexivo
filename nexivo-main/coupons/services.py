"""
Coupon validation logic. Minimal working implementation now; the full
coupons app (model, admin, host-management endpoints) is built out in its
own slice, but bookings needs this importable now since checkout accepts
an optional coupon_code.
"""

from django.core.exceptions import ValidationError


def apply_coupon_preview(*, code, event_id, subtotal):
    """
    Non-locking validation used by the checkout-preview UI (no select_for_update,
    doesn't increment times_used). The authoritative, locking check happens
    again inside create_booking() at actual checkout time.
    """
    from django.core.exceptions import ValidationError
    from django.utils import timezone

    from coupons.models import Coupon
    from events.models import Event

    try:
        coupon = Coupon.objects.get(code__iexact=code, is_active=True)
    except Coupon.DoesNotExist:
        raise ValidationError("Invalid or inactive coupon code.")

    if coupon.event_id and str(coupon.event_id) != str(event_id):
        raise ValidationError("This coupon is not valid for this event.")
    if coupon.valid_from and timezone.now() < coupon.valid_from:
        raise ValidationError("This coupon is not yet active.")
    if coupon.valid_until and timezone.now() > coupon.valid_until:
        raise ValidationError("This coupon has expired.")
    if coupon.max_uses and coupon.times_used >= coupon.max_uses:
        raise ValidationError("This coupon has reached its usage limit.")
    if coupon.min_order_amount and subtotal < coupon.min_order_amount:
        raise ValidationError(f"Minimum order amount for this coupon is {coupon.min_order_amount}.")

    from bookings.services import apply_coupon
    discount = apply_coupon(coupon, subtotal)
    return {
        "valid": True,
        "code": coupon.code,
        "discount_amount": str(discount),
        "discounted_subtotal": str(subtotal - discount),
    }


def validate_and_lock_coupon(*, code, event, customer, subtotal):
    from coupons.models import Coupon
    from django.db import transaction
    from django.utils import timezone

    try:
        coupon = Coupon.objects.select_for_update().get(code__iexact=code, is_active=True)
    except Coupon.DoesNotExist:
        raise ValidationError("Invalid or inactive coupon code.")

    if coupon.event_id and coupon.event_id != event.id:
        raise ValidationError("This coupon is not valid for this event.")
    if coupon.valid_from and timezone.now() < coupon.valid_from:
        raise ValidationError("This coupon is not yet active.")
    if coupon.valid_until and timezone.now() > coupon.valid_until:
        raise ValidationError("This coupon has expired.")
    if coupon.max_uses and coupon.times_used >= coupon.max_uses:
        raise ValidationError("This coupon has reached its usage limit.")
    if coupon.min_order_amount and subtotal < coupon.min_order_amount:
        raise ValidationError(f"Minimum order amount for this coupon is {coupon.min_order_amount}.")

    return coupon
