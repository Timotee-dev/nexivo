"""
Add this to events/models.py at the bottom
OR create a new app: affiliates/models.py
"""
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class EventAffiliate(models.Model):
    """
    A person who promotes a specific event for the host and earns commission.
    The host creates the affiliate program and sets the commission rate.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="affiliates",
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_affiliates_created",
    )
    affiliate_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affiliate_programs",
    )

    # Affiliate details (for non-registered affiliates)
    affiliate_name = models.CharField(max_length=255, blank=True)
    affiliate_email = models.EmailField(blank=True)
    affiliate_phone = models.CharField(max_length=20, blank=True)

    # Unique tracking code
    referral_code = models.CharField(max_length=20, unique=True, db_index=True)

    # Commission set by host — percentage of ticket price
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Percentage of ticket price the affiliate earns e.g. 10.00 = 10%"
    )

    # Wallet
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Bank details for payout
    bank_name = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=255, blank=True)
    paystack_recipient_code = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_affiliates"
        unique_together = [("event", "affiliate_email")]

    def __str__(self):
        return f"{self.affiliate_name or self.affiliate_email} → {self.event.title} ({self.commission_rate}%)"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        import random
        import string
        while True:
            code = "EVT" + "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
            if not EventAffiliate.objects.filter(referral_code=code).exists():
                return code

    @property
    def affiliate_link(self):
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://nexivo.com.ng')
        return f"{frontend_url}/events/{self.event.slug}/?ref={self.referral_code}"


class AffiliateCommission(models.Model):
    """Tracks every commission earned by an event affiliate."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CREDITED = "credited", "Credited"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.ForeignKey(
        EventAffiliate, on_delete=models.CASCADE, related_name="commissions"
    )
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.SET_NULL,
        null=True, related_name="affiliate_commission"
    )
    ticket_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "affiliate_commissions"


class AffiliateWithdrawal(models.Model):
    """Tracks withdrawal requests from event affiliates."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.ForeignKey(
        EventAffiliate, on_delete=models.CASCADE, related_name="withdrawals"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    paystack_transfer_code = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "affiliate_withdrawals"