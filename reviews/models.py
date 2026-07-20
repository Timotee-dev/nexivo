import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """
    A customer's review of an event they attended. Per spec, customers can
    leave reviews and super admin can moderate them. Restricted to customers
    who actually hold (or held) a checked-in/valid ticket for the event,
    to keep ratings meaningful.
    """

    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        FLAGGED = "flagged", "Flagged for Review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written"
    )

    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=150, blank=True, null=True)
    comment = models.TextField()

    moderation_status = models.CharField(
        max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.APPROVED, db_index=True
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviews_moderated",
    )
    moderation_note = models.TextField(blank=True, null=True)

    host_response = models.TextField(blank=True, null=True)
    host_responded_at = models.DateTimeField(blank=True, null=True)

    flagged_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "customer"], name="one_review_per_customer_per_event"),
        ]
        indexes = [
            models.Index(fields=["event", "moderation_status"]),
        ]

    def __str__(self):
        return f"Review({self.rating}★) on {self.event.title} by {self.customer}"


class ReviewFlag(models.Model):
    """A customer/host flagging a review as inappropriate, triggering admin moderation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="flags")
    flagged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_flags"
        constraints = [
            models.UniqueConstraint(fields=["review", "flagged_by"], name="one_flag_per_user_per_review"),
        ]

    def __str__(self):
        return f"Flag on review {self.review_id} by {self.flagged_by}"
