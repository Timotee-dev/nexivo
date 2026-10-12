import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    A single notification sent (or attempted) to a user, across one or more
    channels. Persisted so users have an in-app notification history and so
    delivery failures are visible/retryable.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"
        IN_APP = "in_app", "In-App"

    class EventType(models.TextChoices):
        BOOKING_CONFIRMATION = "booking_confirmation", "Booking Confirmation"
        PAYMENT_CONFIRMATION = "payment_confirmation", "Payment Confirmation"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"
        REFUND_UPDATE = "refund_update", "Refund Update"
        EVENT_REMINDER = "event_reminder", "Event Reminder"
        TICKET_PURCHASED = "ticket_purchased", "Ticket Purchased"
        TICKET_TRANSFER_INITIATED = "ticket_transfer_initiated", "Ticket Transfer Initiated"
        TICKET_TRANSFERRED = "ticket_transferred", "Ticket Transferred"
        PAYOUT_COMPLETED = "payout_completed", "Payout Completed"
        HOST_VERIFICATION_UPDATE = "host_verification_update", "Host Verification Update"
        ANNOUNCEMENT = "announcement", "Platform Announcement"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        READ = "read", "Read"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, db_index=True)
    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)

    subject = models.CharField(max_length=255, blank=True, null=True)
    body = models.TextField()
    context_data = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)

    read_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["recipient", "read_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} -> {self.recipient} ({self.status})"


class NotificationPreference(models.Model):
    """Per-user opt-in/out of channels, beyond legally-required transactional messages."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preference"
    )
    email_enabled = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=True)
    marketing_emails_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preferences"

    def __str__(self):
        return f"Preferences<{self.user.email}>"
