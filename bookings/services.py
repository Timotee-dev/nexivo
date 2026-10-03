"""
Booking/checkout business logic, kept out of views and serializers so it
can be reused by the API, admin actions, and (later) background tasks for
expiring stale reservations.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking, BookingItem
from core.models import PlatformSettings
from events.models import Event, TicketType

RESERVATION_WINDOW_MINUTES = 15


def calculate_processing_fee(subtotal: Decimal) -> Decimal:
    settings_row = PlatformSettings.get_solo()
    percent = Decimal(str(settings_row.payment_processing_fee_percent))
    fixed = Decimal(str(settings_row.payment_processing_fee_fixed))
    percent_fee = (subtotal * percent) / Decimal("100")
    return (percent_fee + fixed).quantize(Decimal("0.01"))


def apply_coupon(coupon, subtotal: Decimal) -> Decimal:
    """Returns the discount amount (not the resulting total) for a given coupon."""
    if coupon.discount_type == coupon.DiscountType.PERCENTAGE:
        discount = (subtotal * coupon.discount_value) / Decimal("100")
        if coupon.max_discount_amount:
            discount = min(discount, coupon.max_discount_amount)
    else:
        discount = coupon.discount_value
    return min(discount, subtotal)


@transaction.atomic
def create_booking(*, customer, event_id, items, coupon_code=None, affiliate_code=None, **kwargs):
    """
    items: list of {"ticket_type_id": <uuid>, "quantity": <int>}
    Locks each TicketType row (select_for_update) to prevent oversell under
    concurrent checkouts, validates sales windows/limits, computes fees, and
    creates a PENDING booking with inventory provisionally reserved.
    The caller (view) is responsible for kicking off payment initialization
    immediately after; if payment never completes, expire_stale_bookings()
    releases the reservation.
    """

    if not items:
        raise ValidationError("At least one ticket item is required.")

    event = Event.objects.select_related("host").get(pk=event_id)
    if event.status != Event.Status.PUBLISHED:
        raise ValidationError("This event is not open for booking.")
    if event.is_past:
        raise ValidationError("This event has already ended.")

    subtotal = Decimal("0")
    booking_items_data = []

    for item in items:
        ticket_type = (
            TicketType.objects.select_for_update()
            .get(pk=item["ticket_type_id"], event=event)
        )
        quantity = int(item["quantity"])

        if quantity < 1:
            raise ValidationError(f"Invalid quantity for {ticket_type.name}.")
        if quantity > ticket_type.max_per_order:
            raise ValidationError(
                f"Maximum {ticket_type.max_per_order} tickets allowed per order for {ticket_type.name}."
            )
        if not ticket_type.is_on_sale:
            raise ValidationError(f"{ticket_type.name} is not currently on sale.")
        if quantity > ticket_type.quantity_remaining:
            raise ValidationError(
                f"Only {ticket_type.quantity_remaining} {ticket_type.name} ticket(s) remaining."
            )

        line_total = ticket_type.current_price * quantity
        subtotal += line_total
        booking_items_data.append((ticket_type, quantity, ticket_type.current_price, line_total))

    coupon = None
    discount_amount = Decimal("0")
    if coupon_code:
        from coupons.services import validate_and_lock_coupon
        coupon = validate_and_lock_coupon(code=coupon_code, event=event, customer=customer, subtotal=subtotal)
        discount_amount = apply_coupon(coupon, subtotal)

    discounted_subtotal = subtotal - discount_amount
    processing_fee = calculate_processing_fee(discounted_subtotal)
    total_amount = discounted_subtotal + processing_fee

    booking = Booking.objects.create(
        customer=customer,
        event=event,
        subtotal=subtotal,
        discount_amount=discount_amount,
        processing_fee=processing_fee,
        total_amount=total_amount,
        coupon=coupon,
        reserved_until=timezone.now() + timezone.timedelta(minutes=RESERVATION_WINDOW_MINUTES),
        customer_name=f"{customer.first_name} {customer.last_name}".strip() or customer.username,
        customer_email=customer.email,
        customer_phone=customer.phone_number,
        affiliate_code=affiliate_code or '',
    )

    for ticket_type, quantity, unit_price, line_total in booking_items_data:
        BookingItem.objects.create(
            booking=booking, ticket_type=ticket_type, quantity=quantity,
            unit_price=unit_price, line_total=line_total,
        )
        ticket_type.reserve(quantity)

    if coupon:
        coupon.times_used = coupon.times_used + 1
        coupon.save(update_fields=["times_used"])

    return booking


@transaction.atomic
def confirm_booking(booking: Booking):
    """
    Called once payment is verified successful. Generates individual Ticket
    rows (one per unit purchased) and marks the booking confirmed. Idempotent:
    safe to call more than once for the same booking (e.g. webhook retries).
    """
    from tickets.services_ticketing import generate_tickets_for_booking

    if booking.status == Booking.Status.CONFIRMED:
        return booking

    booking.status = Booking.Status.CONFIRMED
    booking.confirmed_at = timezone.now()
    booking.save(update_fields=["status", "confirmed_at"])

    generate_tickets_for_booking(booking)

    from django.db.models import F
    from events.models import Event
    Event.objects.filter(pk=booking.event_id).update(
        tickets_sold_count=F("tickets_sold_count") + booking.ticket_count
    )

    # Send confirmation email
    try:
        from notifications.services import notify_booking_confirmed
        notify_booking_confirmed(booking)
    except Exception as e:
        import logging
        logging.getLogger("nexivo").error("Failed to send booking confirmation email: %s", e)

    # Credit marketer commission if event was referred
    try:
        from decimal import Decimal
        from marketers.services import credit_marketer_commission
        nexivo_cut = booking.total_amount * Decimal('0.05')
        credit_marketer_commission(booking, nexivo_cut)
    except Exception as e:
        import logging
        logging.getLogger("nexivo").error("Marketer commission failed: %s", e)

    # Credit affiliate commission if booking came via affiliate link
    try:
        affiliate_code = getattr(booking, 'affiliate_code', None)
        if affiliate_code:
            from affiliates.services import credit_affiliate_commission
            credit_affiliate_commission(booking, affiliate_code)
    except Exception as e:
        import logging
        logging.getLogger("nexivo").error("Affiliate commission failed: %s", e)

    return booking


@transaction.atomic
def cancel_booking(booking: Booking, reason: str = ""):
    """Releases reserved/sold inventory back to the pool and marks booking cancelled."""
    if booking.status in (Booking.Status.CANCELLED, Booking.Status.REFUNDED):
        return booking

    for item in booking.items.select_related("ticket_type").select_for_update():
        item.ticket_type.release(item.quantity)

    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.cancellation_reason = reason
    booking.save(update_fields=["status", "cancelled_at", "cancellation_reason"])
    return booking


def expire_stale_bookings():
    """
    Releases inventory for PENDING bookings whose reservation window has
    lapsed without payment. Intended to run periodically via a scheduled
    task/cron (e.g. every minute).
    """
    stale = Booking.objects.filter(
        status=Booking.Status.PENDING, reserved_until__lt=timezone.now()
    )
    count = 0
    for booking in stale:
        with transaction.atomic():
            for item in booking.items.select_related("ticket_type").select_for_update():
                item.ticket_type.release(item.quantity)
            booking.status = Booking.Status.EXPIRED
            booking.save(update_fields=["status"])
            count += 1
    return count