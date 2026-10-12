from rest_framework import serializers

from coupons.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    times_used = serializers.IntegerField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            "id", "code", "event", "discount_type", "discount_value",
            "max_discount_amount", "min_order_amount", "max_uses", "times_used",
            "valid_from", "valid_until", "is_active", "created_at",
        ]
        read_only_fields = ["id", "times_used", "created_at"]

    def validate(self, attrs):
        if attrs.get("discount_type") == Coupon.DiscountType.PERCENTAGE:
            value = attrs.get("discount_value", getattr(self.instance, "discount_value", None))
            if value is not None and value > 100:
                raise serializers.ValidationError({"discount_value": "Percentage discount cannot exceed 100."})
        valid_from = attrs.get("valid_from")
        valid_until = attrs.get("valid_until")
        if valid_from and valid_until and valid_until <= valid_from:
            raise serializers.ValidationError({"valid_until": "Must be after valid_from."})
        return attrs


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField()
    event_id = serializers.UUIDField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
