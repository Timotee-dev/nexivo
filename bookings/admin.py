import logging

from django.contrib import admin, messages
from django.utils import timezone

from bookings.models import Booking, BookingItem

logger = logging.getLogger("nexivo")


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0
    readonly_fields = ["line_total"]


def force_confirm_booking(modeladmin, request, queryset):
    """
    Admin action: manually confirm a booking, generate tickets, send email.
    Use when a customer paid on Paystack but the webhook never fired.
    Safe to run on already-confirmed bookings — those get their ticket email
    re-sent (no duplicate tickets, no double-counted sales).
    """
    from payments.models import Payment
    from bookings.services import confirm_booking

    confirmed = 0
    resent = 0
    skipped = 0

    for booking in queryset.select_related("customer", "event"):
        try:
            was_confirmed = booking.status == Booking.Status.CONFIRMED

            payment = Payment.objects.filter(
                booking=booking,
                gateway=Payment.Gateway.PAYSTACK,
            ).order_by("-created_at").first()

            if payment and payment.status != Payment.Status.SUCCESSFUL:
                payment.status = Payment.Status.SUCCESSFUL
                payment.paid_at = timezone.now()
                payment.save(update_fields=["status", "paid_at"])

            confirm_booking(booking, force_resend=True)

            if was_confirmed:
                resent += 1
            else:
                confirmed += 1
            logger.info("Admin force-confirmed booking %s", booking.booking_reference)

        except Exception as e:
            logger.error("Force-confirm failed for %s: %s", booking.booking_reference, e)
            skipped += 1
            messages.error(request, f"Failed for {booking.booking_reference}: {e}")

    if confirmed:
        messages.success(request, f"✅ {confirmed} booking(s) confirmed — tickets generated and emails sent.")
    if resent:
        messages.success(request, f"📧 {resent} already-confirmed booking(s) — ticket email re-sent.")
    if skipped:
        messages.warning(request, f"⚠️ {skipped} booking(s) failed — check logs.")


force_confirm_booking.short_description = "⚡ Force confirm + generate tickets + send email"


def release_expired_reservations(modeladmin, request, queryset):
    """
    Admin action: give back tickets held by abandoned checkouts.

    Every pending booking holds its tickets for 15 minutes. If the customer
    never pays, that stock is supposed to be released automatically. This
    button does it on demand across the whole platform (not just the rows you
    selected) — run it if an event starts reporting "sold out" or
    "not currently on sale" while tickets clearly remain.
    """
    from bookings.services import expire_stale_bookings

    try:
        count = expire_stale_bookings()
    except Exception as e:
        logger.error("Manual release_expired_reservations failed: %s", e)
        messages.error(request, f"Failed to release reservations: {e}")
        return

    if count:
        messages.success(
            request,
            f"♻️ Released {count} expired reservation(s) — those tickets are back on sale.",
        )
    else:
        messages.info(request, "Nothing to release — no expired reservations are holding stock.")


release_expired_reservations.short_description = "♻️ Release expired reservations (frees stuck tickets)"


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["booking_reference", "customer", "event", "status", "total_amount", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["booking_reference", "customer__email", "event__title"]
    readonly_fields = ["id", "booking_reference", "created_at", "updated_at"]
    inlines = [BookingItemInline]
    actions = [force_confirm_booking, release_expired_reservations]
