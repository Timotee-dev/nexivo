import uuid

from django.core.exceptions import ValidationError
from django.db import models


class PlatformSettings(models.Model):
    """
    Singleton table holding global, super-admin-editable platform configuration.
    Only one row may ever exist (id is pinned to 1).
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    platform_name = models.CharField(max_length=100, default="Nexivo")

    # Commission: spec default is 95% host / 5% platform, but kept configurable.
    platform_commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        help_text="Percentage of each ticket sale retained by Nexivo.",
    )

    # Processing fee passed on to the customer (on top of ticket price).
    payment_processing_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.50
    )
    payment_processing_fee_fixed = models.DecimalField(
        max_digits=8, decimal_places=2, default=100.00,
        help_text="Flat fee in NGN added per transaction, on top of the percentage fee.",
    )

    require_nin_for_paid_tickets = models.BooleanField(default=True)
    require_email_verification = models.BooleanField(default=True)
    maintenance_mode = models.BooleanField(default=False)

    refund_window_hours = models.PositiveIntegerField(
        default=72, help_text="Hours before event start that refunds are allowed."
    )
    refund_processing_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.50
    )

    payout_delay_hours = models.PositiveIntegerField(
        default=24,
        help_text="Hours after event completion before host payout is released.",
    )

    support_email = models.EmailField(default="support@nexivo.com")
    support_phone = models.CharField(max_length=20, blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("PlatformSettings is a singleton and cannot be deleted.")

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Platform Settings"


class Announcement(models.Model):
    """Platform-wide announcements managed by super admin."""

    class Audience(models.TextChoices):
        ALL = "all", "Everyone"
        HOSTS = "hosts", "Hosts Only"
        CUSTOMERS = "customers", "Customers Only"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="announcements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "announcements"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_active", "audience"])]

    def __str__(self):
        return self.title


class PlatformFee(models.Model):
    """
    Historical snapshot of commission/fee rates, captured whenever PlatformSettings
    changes, so past transactions reconcile against the rate active at sale time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform_commission_percent = models.DecimalField(max_digits=5, decimal_places=2)
    payment_processing_fee_percent = models.DecimalField(max_digits=5, decimal_places=2)
    payment_processing_fee_fixed = models.DecimalField(max_digits=8, decimal_places=2)
    effective_from = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "platform_fee_history"
        ordering = ["-effective_from"]

    def __str__(self):
        return f"Fee snapshot @ {self.effective_from}"
