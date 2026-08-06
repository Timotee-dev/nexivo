from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserPublicSerializer
from events.models import Category, Event, EventGallery, TicketType


class CategorySerializer(serializers.ModelSerializer):
    event_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "icon", "is_active", "display_order", "event_count"]
        read_only_fields = ["id", "slug"]


class EventGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = EventGallery
        fields = ["id", "image", "caption", "display_order"]
        read_only_fields = ["id"]


class TicketTypeSerializer(serializers.ModelSerializer):
    is_sold_out = serializers.BooleanField(read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)

    class Meta:
        model = TicketType
        fields = [
            "id", "name", "description", "is_free", "price", "currency",
            "quantity_total", "quantity_remaining", "max_per_order",
            "sales_start", "sales_end", "is_early_bird", "early_bird_deadline",
            "perks", "is_active", "display_order", "is_sold_out", "is_on_sale",
            "created_at",
        ]
        read_only_fields = ["id", "quantity_remaining", "created_at"]

    def validate(self, attrs):
        if attrs.get("price", 0) == 0:
            attrs["is_free"] = True
        sales_start = attrs.get("sales_start")
        sales_end = attrs.get("sales_end")
        if sales_start and sales_end and sales_end <= sales_start:
            raise serializers.ValidationError({"sales_end": "Must be after sales start."})
        return attrs


class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list/search views — avoids N+1 nested ticket data."""

    host = UserPublicSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    min_price = serializers.SerializerMethodField()
    is_upcoming = serializers.BooleanField(read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    distance_km = serializers.FloatField(read_only=True, required=False)

    class Meta:
        model = Event
        fields = [
            "id", "title", "slug", "short_description", "event_type", "status",
            "host", "category", "banner_image", "city", "state", "country",
            "start_datetime", "end_datetime", "is_featured", "min_price",
            "is_upcoming", "is_sold_out", "tickets_sold_count", "favorite_count",
            "average_rating", "review_count", "distance_km",
        ]
        read_only_fields = fields

    def get_min_price(self, obj):
        prices = [tt.price for tt in obj.ticket_types.all() if tt.is_active]
        return min(prices) if prices else None


class EventDetailSerializer(serializers.ModelSerializer):
    host = UserPublicSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True, required=False
    )
    ticket_types = TicketTypeSerializer(many=True, read_only=True)
    gallery_images = EventGallerySerializer(many=True, read_only=True)

    is_upcoming = serializers.BooleanField(read_only=True)
    is_live = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    is_physical = serializers.BooleanField(read_only=True)
    is_virtual = serializers.BooleanField(read_only=True)
    total_tickets_remaining = serializers.IntegerField(read_only=True)
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id", "host", "category", "category_id", "title", "slug",
            "description", "short_description", "event_type", "status",
            "venue_name", "address", "city", "state", "country", "latitude", "longitude",
            "virtual_platform", "virtual_join_url", "virtual_access_instructions",
            "start_datetime", "end_datetime", "timezone_name", "banner_image",
            "is_featured", "max_capacity", "view_count", "tickets_sold_count",
            "favorite_count", "average_rating", "review_count",
            "requires_age_verification", "minimum_age", "refund_policy",
            "terms_and_conditions", "ticket_types", "gallery_images",
            "is_upcoming", "is_live", "is_past", "is_sold_out", "is_physical",
            "is_virtual", "total_tickets_remaining", "is_favorited",
            "published_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "host", "slug", "status", "view_count", "tickets_sold_count",
            "favorite_count", "average_rating", "review_count",
            "published_at", "created_at", "updated_at",
        ]

    def get_is_favorited(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, "customer_profile", None)
        return bool(profile and profile.favorite_events.filter(pk=obj.pk).exists())

    def validate(self, attrs):
        event_type = attrs.get("event_type", getattr(self.instance, "event_type", None))
        start = attrs.get("start_datetime", getattr(self.instance, "start_datetime", None))
        end = attrs.get("end_datetime", getattr(self.instance, "end_datetime", None))

        if start and end and end <= start:
            raise serializers.ValidationError({"end_datetime": "Must be after start time."})

        if event_type in (Event.EventType.PHYSICAL, Event.EventType.HYBRID):
            venue = attrs.get("venue_name", getattr(self.instance, "venue_name", None))
            city = attrs.get("city", getattr(self.instance, "city", None))
            if not (venue and city):
                raise serializers.ValidationError(
                    "Venue name and city are required for physical/hybrid events."
                )

        if event_type in (Event.EventType.VIRTUAL, Event.EventType.HYBRID):
            platform = attrs.get("virtual_platform", getattr(self.instance, "virtual_platform", None))
            if not platform:
                raise serializers.ValidationError(
                    "Virtual platform is required for virtual/hybrid events."
                )

        return attrs


class TicketTypeInputSerializer(serializers.Serializer):
    """Simple input serializer for ticket types during event creation."""
    name = serializers.CharField(max_length=100)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity_total = serializers.IntegerField(min_value=1)
    max_per_order = serializers.IntegerField(default=10)
    description = serializers.CharField(default='', allow_blank=True, required=False)


class EventCreateSerializer(EventDetailSerializer):
    """
    Create serializer accepting nested ticket_types so a host can submit
    the full event + ticket tiers in one request.
    """

    ticket_types = TicketTypeInputSerializer(many=True, required=False)
    marketer_referral_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    @transaction.atomic
    def create(self, validated_data):
        ticket_types_data = validated_data.pop("ticket_types", [])
        validated_data["host"] = self.context["request"].user
        event = Event.objects.create(**validated_data)

        for tt_data in ticket_types_data:
            if not tt_data.get("name"):
                continue
            TicketType.objects.create(
                event=event,
                name=tt_data.get("name", ""),
                price=tt_data.get("price", 0),
                quantity_total=tt_data.get("quantity_total", 0),
                quantity_remaining=tt_data.get("quantity_total", 0),
                max_per_order=tt_data.get("max_per_order", 10),
                description=tt_data.get("description", ""),
            )

        return event


class EventModerationSerializer(serializers.ModelSerializer):
    """Super-admin-only serializer for moderation actions (suspend/feature an event)."""

    class Meta:
        model = Event
        fields = ["id", "status", "is_featured", "featured_until"]
        read_only_fields = ["id"]