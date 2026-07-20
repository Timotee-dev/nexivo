import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    """
    Event categories (Music, Conference, Sports, Comedy, Workshop, etc).
    Managed exclusively by super admin per spec; read-only for everyone else.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Icon identifier/class name for frontend rendering, e.g. 'music', 'briefcase'.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Event(models.Model):
    """
    Core event entity. Supports physical, virtual, and hybrid formats.
    Hosts own events; super admin can moderate/delete any event.
    """

    class EventType(models.TextChoices):
        PHYSICAL = "physical", "Physical"
        VIRTUAL = "virtual", "Virtual"
        HYBRID = "hybrid", "Hybrid"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Pending Review"
        PUBLISHED = "published", "Published"
        SUSPENDED = "suspended", "Suspended"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_events"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name="events"
    )

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True, null=True)

    event_type = models.CharField(
        max_length=20, choices=EventType.choices, default=EventType.PHYSICAL, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    # Physical location (required for physical/hybrid)
    venue_name = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    country = models.CharField(max_length=100, default="Nigeria")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    # Virtual location (required for virtual/hybrid)
    virtual_platform = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="e.g. Zoom, Google Meet, YouTube Live, custom stream URL.",
    )
    virtual_join_url = models.URLField(blank=True, null=True)
    virtual_access_instructions = models.TextField(blank=True, null=True)

    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField()
    timezone_name = models.CharField(max_length=64, default="Africa/Lagos")

    banner_image = models.ImageField(upload_to="event_banners/%Y/%m/", blank=True, null=True)

    is_featured = models.BooleanField(default=False, db_index=True)
    featured_until = models.DateTimeField(blank=True, null=True)

    max_capacity = models.PositiveIntegerField(
        blank=True, null=True, help_text="Optional overall cap across all ticket types."
    )

    # Denormalized counters, kept in sync by signals/services for fast list rendering.
    view_count = models.PositiveIntegerField(default=0)
    tickets_sold_count = models.PositiveIntegerField(default=0)
    favorite_count = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)

    requires_age_verification = models.BooleanField(default=False)
    minimum_age = models.PositiveSmallIntegerField(blank=True, null=True)

    refund_policy = models.TextField(blank=True, null=True)
    terms_and_conditions = models.TextField(blank=True, null=True)

    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "events"
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["status", "start_datetime"]),
            models.Index(fields=["event_type", "status"]),
            models.Index(fields=["city", "state"]),
            models.Index(fields=["is_featured", "status"]),
            models.Index(fields=["host", "status"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:260]
            candidate = base_slug
            suffix = 0
            while Event.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base_slug}-{suffix}"
            self.slug = candidate
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        if self.end_datetime <= self.start_datetime:
            errors["end_datetime"] = "End time must be after start time."

        if self.event_type in (self.EventType.PHYSICAL, self.EventType.HYBRID):
            if not self.venue_name or not self.address or not self.city:
                errors["venue_name"] = (
                    "Venue name, address, and city are required for physical/hybrid events."
                )

        if self.event_type in (self.EventType.VIRTUAL, self.EventType.HYBRID):
            if not self.virtual_platform:
                errors["virtual_platform"] = (
                    "Virtual platform is required for virtual/hybrid events."
                )

        if errors:
            raise ValidationError(errors)

    @property
    def is_physical(self):
        return self.event_type in (self.EventType.PHYSICAL, self.EventType.HYBRID)

    @property
    def is_virtual(self):
        return self.event_type in (self.EventType.VIRTUAL, self.EventType.HYBRID)

    @property
    def is_upcoming(self):
        return self.start_datetime > timezone.now()

    @property
    def is_live(self):
        now = timezone.now()
        return self.start_datetime <= now <= self.end_datetime

    @property
    def is_past(self):
        return self.end_datetime < timezone.now()

    @property
    def total_tickets_available(self):
        agg = self.ticket_types.aggregate(total=models.Sum("quantity_total"))
        return agg["total"] or 0

    @property
    def total_tickets_remaining(self):
        agg = self.ticket_types.aggregate(total=models.Sum("quantity_remaining"))
        return agg["total"] or 0

    @property
    def is_sold_out(self):
        return self.ticket_types.exists() and self.total_tickets_remaining == 0

    def publish(self):
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])


class EventGallery(models.Model):
    """Additional photos/media for an event, beyond the main banner."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.ImageField(upload_to="event_gallery/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_gallery"
        ordering = ["display_order", "created_at"]
        verbose_name_plural = "event gallery images"

    def __str__(self):
        return f"Image for {self.event.title}"


class TicketType(models.Model):
    """
    A purchasable ticket tier within an event (VIP, Regular, Free, Early Bird, etc).
    Hosts may create an unlimited number of these per event.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="ticket_types")

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    is_free = models.BooleanField(default=False, db_index=True)
    price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default="NGN")

    quantity_total = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_remaining = models.PositiveIntegerField()
    max_per_order = models.PositiveIntegerField(default=10)

    sales_start = models.DateTimeField(blank=True, null=True)
    sales_end = models.DateTimeField(blank=True, null=True)

    is_early_bird = models.BooleanField(default=False)
    early_bird_deadline = models.DateTimeField(blank=True, null=True)

    perks = models.JSONField(
        default=list, blank=True,
        help_text="List of perk strings, e.g. ['Backstage access', 'Free drink', 'Meet & greet'].",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ticket_types"
        ordering = ["display_order", "price"]
        indexes = [
            models.Index(fields=["event", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.event.title}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.quantity_remaining is None:
            self.quantity_remaining = self.quantity_total
        if self.price == 0:
            self.is_free = True
        super().save(*args, **kwargs)

    def clean(self):
        if self.quantity_remaining is not None and self.quantity_remaining > self.quantity_total:
            raise ValidationError(
                {"quantity_remaining": "Cannot exceed total quantity."}
            )
        if self.sales_start and self.sales_end and self.sales_end <= self.sales_start:
            raise ValidationError({"sales_end": "Sales end must be after sales start."})

    @property
    def is_sold_out(self):
        return self.quantity_remaining <= 0

    @property
    def is_on_sale(self):
        now = timezone.now()
        if not self.is_active or self.is_sold_out:
            return False
        if self.sales_start and now < self.sales_start:
            return False
        if self.sales_end and now > self.sales_end:
            return False
        return True

    @property
    def current_price(self):
        """Returns the effective price, accounting for an active early-bird window."""
        if self.is_early_bird and self.early_bird_deadline and timezone.now() <= self.early_bird_deadline:
            return self.price
        return self.price

    def reserve(self, count=1):
        """
        Atomically decrement remaining inventory. Raises ValidationError if
        insufficient stock. Callers should wrap this in a transaction with
        select_for_update to avoid oversell race conditions under concurrency.
        """
        if count > self.quantity_remaining:
            raise ValidationError("Not enough tickets remaining for this ticket type.")
        self.quantity_remaining = models.F("quantity_remaining") - count
        self.save(update_fields=["quantity_remaining"])

    def release(self, count=1):
        """Returns reserved inventory back to the pool (e.g. on cancelled/expired booking)."""
        self.quantity_remaining = models.F("quantity_remaining") + count
        self.save(update_fields=["quantity_remaining"])
