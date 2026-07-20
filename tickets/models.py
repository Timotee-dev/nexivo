import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Ticket(models.Model):
    """
    A single, individually-scannable ticket. One BookingItem of quantity N
    generates N Ticket rows, each with its own unique QR/barcode so each
    attendee can be checked in independently.
    """

    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        USED = "used", "Used"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
        TRANSFERRED = "transferred", "Transferred"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_item = models.ForeignKey(
        "bookings.BookingItem", on_delete=models.CASCADE, related_name="tickets"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="tickets"
    )
    ticket_type = models.ForeignKey(
        "events.TicketType", on_delete=models.CASCADE, related_name="tickets"
    )

    # The current holder — initially the purchaser, changes on transfer.
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="held_tickets"
    )
    holder_name = models.CharField(max_length=255)
    holder_email = models.EmailField()

    # Unique scan code — random, not sequential/guessable. Encoded into the QR.
    ticket_code = models.CharField(max_length=40, unique=True, db_index=True)
    barcode_value = models.CharField(max_length=40, unique=True, db_index=True)

    qr_image = models.ImageField(upload_to="ticket_qr/%Y/%m/", blank=True, null=True)
    pdf_file = models.FileField(upload_to="ticket_pdf/%Y/%m/", blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.VALID, db_index=True
    )

    checked_in_at = models.DateTimeField(blank=True, null=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="checkins_performed",
    )

    seat_label = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tickets"
        indexes = [
            models.Index(fields=["event", "status"]),
            models.Index(fields=["holder", "status"]),
            models.Index(fields=["ticket_code"]),
        ]

    def __str__(self):
        return f"Ticket {self.ticket_code} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            self.ticket_code = self._generate_unique_code(field="ticket_code")
        if not self.barcode_value:
            self.barcode_value = self._generate_unique_code(field="barcode_value", numeric=True)
        super().save(*args, **kwargs)

    @classmethod
    def _generate_unique_code(cls, field, numeric=False):
        while True:
            if numeric:
                candidate = "".join(secrets.choice("0123456789") for _ in range(16))
            else:
                candidate = "NXV" + secrets.token_hex(10).upper()
            if not cls.objects.filter(**{field: candidate}).exists():
                return candidate

    @property
    def is_checked_in(self):
        return self.status == self.Status.USED

    @property
    def can_be_transferred(self):
        return self.status == self.Status.VALID and not self.is_checked_in

    @property
    def can_be_checked_in(self):
        return self.status == self.Status.VALID


class TicketScanLog(models.Model):
    """
    Immutable record of every scan attempt at the door — including rejected
    duplicate scans — so hosts get a full audit trail and the scanner app
    can show 'already used at HH:MM by scanner X' instead of a bare error.
    """

    class Result(models.TextChoices):
        SUCCESS = "success", "Checked In"
        DUPLICATE = "duplicate", "Duplicate Scan"
        INVALID = "invalid", "Invalid Code"
        WRONG_EVENT = "wrong_event", "Wrong Event"
        CANCELLED_TICKET = "cancelled_ticket", "Ticket Cancelled/Refunded"
        NOT_YET_VALID = "not_yet_valid", "Event Not Started"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name="scan_logs"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="scan_logs"
    )
    scanned_code = models.CharField(max_length=40)
    result = models.CharField(max_length=20, choices=Result.choices, db_index=True)
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="scans_performed"
    )

    # Offline sync support: scanner app records the original scan time client-side
    # even if it can't reach the server until later; client_scanned_at preserves that,
    # while created_at reflects when the server actually recorded it.
    client_scanned_at = models.DateTimeField(
        blank=True, null=True,
        help_text="Timestamp recorded on-device at scan time, used when syncing offline scans.",
    )
    was_offline_sync = models.BooleanField(default=False)
    device_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "ticket_scan_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "result"]),
            models.Index(fields=["ticket", "created_at"]),
        ]

    def __str__(self):
        return f"Scan({self.result}) on {self.scanned_code}"


class TicketTransfer(models.Model):
    """Record of a ticket being transferred from one holder to another."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Acceptance"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled by Sender"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="transfers")
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ticket_transfers_sent"
    )
    to_email = models.EmailField()
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ticket_transfers_received",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    transfer_code = models.CharField(max_length=40, unique=True, db_index=True)
    message = models.CharField(max_length=255, blank=True, null=True)

    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_transfers"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transfer of {self.ticket.ticket_code} to {self.to_email}"

    def save(self, *args, **kwargs):
        if not self.transfer_code:
            self.transfer_code = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and timezone.now() > self.expires_at
