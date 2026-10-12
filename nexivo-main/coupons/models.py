import secrets
import uuid

from django.conf import settings
from django.db import models


class Coupon(models.Model):
    """
    Discount code. Can be platform-wide (created by super admin) or scoped
    to a single host's event (created by the host). Per spec: hosts manage
    coupons for their own events; super admin can manage any coupon.
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed Amount"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupons_created"
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="coupons",
        null=True, blank=True,
        help_text="Leave blank for a platform-wide coupon (super admin only).",
    )

    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Caps the discount for percentage-type coupons.",
    )
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    max_uses = models.PositiveIntegerField(blank=True, null=True)
    times_used = models.PositiveIntegerField(default=0)

    valid_from = models.DateTimeField(blank=True, null=True)
    valid_until = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coupons"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_hex(4).upper()
        self.code = self.code.upper()
        super().save(*args, **kwargs)
