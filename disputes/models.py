import uuid

from django.conf import settings
from django.db import models


class Dispute(models.Model):
    class Category(models.TextChoices):
        PAYMENT_NOT_RECEIVED = "payment_not_received", "Payment Not Received"
        REFUND_NOT_PROCESSED = "refund_not_processed", "Refund Not Processed"
        EVENT_CANCELLED = "event_cancelled", "Event Cancelled Without Notice"
        TICKET_INVALID = "ticket_invalid", "Ticket Was Invalid at Entry"
        FRAUD = "fraud", "Fraudulent Activity"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under Review"
        AWAITING_HOST = "awaiting_host", "Awaiting Host Response"
        AWAITING_CUSTOMER = "awaiting_customer", "Awaiting Customer Response"
        RESOLVED_CUSTOMER = "resolved_customer", "Resolved — Customer Favour"
        RESOLVED_HOST = "resolved_host", "Resolved — Host Favour"
        CLOSED = "closed", "Closed"

    class Resolution(models.TextChoices):
        FULL_REFUND = "full_refund", "Full Refund Issued"
        PARTIAL_REFUND = "partial_refund", "Partial Refund Issued"
        NO_REFUND = "no_refund", "No Refund — Host Favour"
        ACCOUNT_ACTIONED = "account_actioned", "Account Actioned"
        ESCALATED = "escalated", "Escalated to Legal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=20, unique=True, db_index=True)

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes_raised"
    )
    against_host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes_against"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="disputes_assigned", limit_choices_to={"role": "super_admin"},
    )

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="disputes",
    )
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="disputes",
    )

    category = models.CharField(max_length=40, choices=Category.choices, db_index=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    resolution = models.CharField(
        max_length=30, choices=Resolution.choices, blank=True, null=True
    )

    subject = models.CharField(max_length=255)
    description = models.TextField()
    resolution_notes = models.TextField(blank=True, null=True)

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="disputes_resolved",
    )
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "disputes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            import random, string
            while True:
                ref = "DSP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
                if not Dispute.objects.filter(reference=ref).exists():
                    self.reference = ref
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Dispute {self.reference} ({self.status})"


class DisputeMessage(models.Model):
    """Thread of messages between customer, host, and admin on a dispute."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    attachment = models.FileField(upload_to="dispute_attachments/%Y/%m/", blank=True, null=True)
    is_internal = models.BooleanField(
        default=False, help_text="Internal admin note, not visible to customer/host."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dispute_messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"Message on {self.dispute.reference} by {self.author}"
