from rest_framework import serializers

from bookings.models import Booking, BookingItem
from events.serializers import EventListSerializer


class BookingItemSerializer(serializers.ModelSerializer):
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)

    class Meta:
        model = BookingItem
        fields = ["id", "ticket_type", "ticket_type_name", "quantity", "unit_price", "line_total"]
        read_only_fields = fields


class BookingItemInputSerializer(serializers.Serializer):
    ticket_type_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    """POST body for initiating a booking/checkout."""

    event_id = serializers.UUIDField()
    items = BookingItemInputSerializer(many=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gateway = serializers.ChoiceField(choices=["paystack", "flutterwave", "stripe"])


class BookingSerializer(serializers.ModelSerializer):
    items = BookingItemSerializer(many=True, read_only=True)
    event = EventListSerializer(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    ticket_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "booking_reference", "event", "status", "subtotal",
            "discount_amount", "processing_fee", "total_amount", "currency",
            "reserved_until", "customer_name", "customer_email", "customer_phone",
            "items", "is_expired", "ticket_count", "confirmed_at", "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
