import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Booking(models.Model):
    """
    A single checkout transaction. One Booking can contain multiple tickets
    (possibly across multiple ticket types) for one event, purchased by one
    customer in one go. Payment lives in the payments app and references
    this booking 1:1.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_reference = models.CharField(max_length=20, unique=True, db_index=True)

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="bookings"
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    processing_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")

    coupon = models.ForeignKey(
        "coupons.Coupon", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bookings",
    )

    # Reservation expiry: inventory is held for this window while the customer pays.
    reserved_until = models.DateTimeField()

    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)

    confirmed_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["status", "reserved_until"]),
        ]

    def __str__(self):
        return f"Booking {self.booking_reference} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        import random
        import string
        while True:
            ref = "NXV-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Booking.objects.filter(booking_reference=ref).exists():
                return ref

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and timezone.now() > self.reserved_until

    @property
    def ticket_count(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0


class BookingItem(models.Model):
    """A line item within a booking: N tickets of one ticket type."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="items")
    ticket_type = models.ForeignKey(
        "events.TicketType", on_delete=models.CASCADE, related_name="booking_items"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "booking_items"

    def __str__(self):
        return f"{self.quantity}x {self.ticket_type.name} ({self.booking.booking_reference})"

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)
