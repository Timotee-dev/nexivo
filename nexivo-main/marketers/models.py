"""
Marketer app models.
Add this as a new app: marketers/models.py
"""
import secrets
import uuid

from django.conf import settings
from django.db import models


class Marketer(models.Model):
    """A user who refers event organizers to Nexivo and earns commission."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="marketer_profile",
    )
    referral_code = models.CharField(max_length=20, unique=True, db_index=True)

    # Wallet
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Bank details for automatic Paystack transfers
    bank_name = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=255, blank=True)
    paystack_recipient_code = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "marketers"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.referral_code})"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        import random
        import string
        while True:
            code = "NXM" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Marketer.objects.filter(referral_code=code).exists():
                return code


class MarketerCommission(models.Model):
    """Tracks every commission earned by a marketer."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CREDITED = "credited", "Credited"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    marketer = models.ForeignKey(
        Marketer, on_delete=models.CASCADE, related_name="commissions"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.SET_NULL, null=True, related_name="marketer_commissions"
    )
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.SET_NULL, null=True, related_name="marketer_commission"
    )
    ticket_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    nexivo_cut = models.DecimalField(max_digits=12, decimal_places=2)  # 5% of ticket revenue
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)  # 10% of nexivo_cut
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketer_commissions"

    def __str__(self):
        return f"{self.marketer.referral_code} - ₦{self.commission_amount}"


class MarketerWithdrawal(models.Model):
    """Tracks withdrawal requests and Paystack transfer status."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    marketer = models.ForeignKey(
        Marketer, on_delete=models.CASCADE, related_name="withdrawals"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    paystack_transfer_code = models.CharField(max_length=100, blank=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "marketer_withdrawals"

    def __str__(self):
        return f"{self.marketer.referral_code} - ₦{self.amount} ({self.status})"