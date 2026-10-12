import uuid

from django.conf import settings
from django.db import models


class Payout(models.Model):
    """
    A scheduled or completed transfer of a host's accumulated earnings to
    their bank account. Since split payments already route the host's share
    to their gateway subaccount at the time of sale, a Payout record here
    primarily tracks the *release* of those funds to the host's actual bank
    account (most gateway subaccounts settle on their own T+1/T+2 schedule;
    this model gives Nexivo's super admin visibility and an override/hold
    capability, e.g. for disputes).
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        HELD = "held", "Held for Review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payouts"
    )
    payments = models.ManyToManyField(
        "payments.Payment", related_name="payouts",
        help_text="The successful payments whose host_payout_amount this payout covers.",
    )

    gateway = models.CharField(max_length=20, choices=[
        ("paystack", "Paystack"), ("flutterwave", "Flutterwave"), ("stripe", "Stripe"),
    ])
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    scheduled_for = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)

    gateway_transfer_id = models.CharField(max_length=255, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    held_reason = models.TextField(blank=True, null=True)
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payouts_held",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payouts"
        ordering = ["-scheduled_for"]
        indexes = [
            models.Index(fields=["host", "status"]),
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return f"Payout({self.host}, {self.amount}, {self.status})"


class PayoutLedgerEntry(models.Model):
    """
    Append-only ledger of every event that affects a host's payable balance:
    a successful sale (credit), a payout being scheduled/sent (debit), or a
    refund deducted from future payouts (debit). Lets super admin reconstruct
    exactly how a host's current balance was derived at any point in time.
    """

    class EntryType(models.TextChoices):
        SALE_CREDIT = "sale_credit", "Sale Credit"
        PAYOUT_DEBIT = "payout_debit", "Payout Debit"
        REFUND_DEBIT = "refund_debit", "Refund Debit"
        ADJUSTMENT = "adjustment", "Manual Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payout_ledger_entries"
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices, db_index=True)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Positive for credits, negative for debits.",
    )
    related_payment = models.ForeignKey(
        "payments.Payment", on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    related_payout = models.ForeignKey(
        Payout, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    note = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "payout_ledger_entries"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["host", "created_at"])]

    def __str__(self):
        return f"{self.entry_type}({self.amount}) for {self.host}"
