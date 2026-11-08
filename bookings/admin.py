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
    Safe to run on already-confirmed bookings (idempotent).
    """
    from payments.models import Payment

    confirmed = 0
    skipped = 0

    for booking in queryset.select_related("customer", "event"):
        try:
            # Mark payment as successful if it exists and is still pending
            payment = Payment.objects.filter(
                booking=booking,
                gateway=Payment.Gateway.PAYSTACK,
            ).order_by("-created_at").first()

            if payment and payment.status != Payment.Status.SUCCESSFUL:
                payment.status = Payment.Status.SUCCESSFUL
                payment.paid_at = timezone.now()
                payment.save(update_fields=["status", "paid_at"])

            # Confirm booking + generate tickets + send email
            from bookings.services import confirm_booking
            confirm_booking(booking)
            confirmed += 1
            logger.info("Admin force-confirmed booking %s", booking.booking_reference)

        except Exception as e:
            logger.error("Force-confirm failed for %s: %s", booking.booking_reference, e)
            skipped += 1
            messages.error(request, f"Failed for {booking.booking_reference}: {e}")

    if confirmed:
        messages.success(request, f"✅ {confirmed} booking(s) confirmed — tickets generated and emails sent.")
    if skipped:
        messages.warning(request, f"⚠️ {skipped} booking(s) failed — check logs.")


force_confirm_booking.short_description = "⚡ Force confirm + generate tickets + send email"


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["booking_reference", "customer", "event", "status", "total_amount", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["booking_reference", "customer__email", "event__title"]
    readonly_fields = ["id", "booking_reference", "created_at", "updated_at"]
    inlines = [BookingItemInline]
    actions = [force_confirm_booking]
