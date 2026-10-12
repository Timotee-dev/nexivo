import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    """
    A single payment transaction against a Booking. One Booking has exactly
    one Payment (re-attempted payments create a new Payment row tied to the
    same booking rather than mutating a failed one, preserving a full
    attempt history for reconciliation/fraud review).
    """

    class Gateway(models.TextChoices):
        PAYSTACK = "paystack", "Paystack"
        FLUTTERWAVE = "flutterwave", "Flutterwave"
        STRIPE = "stripe", "Stripe"

    class Status(models.TextChoices):
        INITIALIZED = "initialized", "Initialized"
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
        DISPUTED = "disputed", "Disputed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.CASCADE, related_name="payments"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )

    gateway = models.CharField(max_length=20, choices=Gateway.choices, db_index=True)
    gateway_reference = models.CharField(
        max_length=255, db_index=True,
        help_text="Our reference sent to the gateway (e.g. Paystack 'reference').",
    )
    gateway_transaction_id = models.CharField(
        max_length=255, blank=True, null=True, db_index=True,
        help_text="The gateway's own transaction/charge ID, populated after verification.",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")

    # Split breakdown, computed at initialization time using the platform
    # commission rate active *right now* (snapshotted onto the payment so
    # later rate changes never retroactively alter historical transactions).
    platform_commission_percent = models.DecimalField(max_digits=5, decimal_places=2)
    platform_commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    host_payout_amount = models.DecimalField(max_digits=12, decimal_places=2)

    checkout_url = models.URLField(blank=True, null=True)
    authorization_data = models.JSONField(default=dict, blank=True)
    invoice_pdf = models.FileField(upload_to="invoices/%Y/%m/", blank=True, null=True, max_length=500)

    paid_at = models.DateTimeField(blank=True, null=True)
    failed_reason = models.TextField(blank=True, null=True)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    risk_score = models.PositiveSmallIntegerField(
        default=0, help_text="0-100 fraud risk score; higher = riskier. Set by fraud checks."
    )
    flagged_for_review = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gateway", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["flagged_for_review"]),
        ]

    def __str__(self):
        return f"Payment {self.gateway_reference} ({self.status})"


class WebhookEvent(models.Model):
    """
    Raw inbound webhook log, kept for every gateway notification received —
    verified or not — for audit, retry, and reconciliation purposes.
    Idempotency: gateway + event_id is unique, so replayed webhooks
    (gateways commonly retry on timeout) are detected and ignored safely.
    """

    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Received"
        VERIFIED = "verified", "Signature Verified"
        REJECTED = "rejected", "Signature Rejected"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Processing Failed"
        DUPLICATE = "duplicate", "Duplicate (Ignored)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(max_length=20, choices=Payment.Gateway.choices, db_index=True)
    event_type = models.CharField(max_length=100, blank=True, null=True)
    event_id = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Gateway-provided unique event/notification ID, used for idempotency.",
    )
    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.RECEIVED, db_index=True
    )
    related_payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="webhook_events"
    )

    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "webhook_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "event_id"],
                name="unique_gateway_event_id",
                condition=models.Q(event_id__isnull=False),
            )
        ]
        indexes = [
            models.Index(fields=["gateway", "status"]),
        ]

    def __str__(self):
        return f"WebhookEvent({self.gateway}, {self.event_type}, {self.status})"


class Refund(models.Model):
    """A refund issued against a Payment, full or partial."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="refunds_requested"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="refunds_approved",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    processing_fee_deducted = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)

    gateway_refund_id = models.CharField(max_length=255, blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "refunds"
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Refund({self.amount}, {self.status}) for {self.payment.gateway_reference}"


class ReconciliationRecord(models.Model):
    """
    Result of comparing our internal Payment records against the gateway's
    transaction list for a given period, surfacing mismatches (amount
    discrepancies, missing local records, missing gateway records) for
    finance/super-admin review.
    """

    class Discrepancy(models.TextChoices):
        NONE = "none", "Matched"
        AMOUNT_MISMATCH = "amount_mismatch", "Amount Mismatch"
        MISSING_LOCALLY = "missing_locally", "Found on Gateway, Missing Locally"
        MISSING_ON_GATEWAY = "missing_on_gateway", "Found Locally, Missing on Gateway"
        STATUS_MISMATCH = "status_mismatch", "Status Mismatch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(max_length=20, choices=Payment.Gateway.choices)
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="reconciliation_records"
    )
    gateway_transaction_id = models.CharField(max_length=255)
    local_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    gateway_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    discrepancy_type = models.CharField(max_length=30, choices=Discrepancy.choices, db_index=True)
    notes = models.TextField(blank=True, null=True)
    resolved = models.BooleanField(default=False, db_index=True)
    run_date = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reconciliation_records"
        ordering = ["-run_date"]

    def __str__(self):
        return f"Reconciliation({self.gateway_transaction_id}, {self.discrepancy_type})"