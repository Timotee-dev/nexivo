from rest_framework import serializers

from accounts.serializers import UserPublicSerializer
from reviews.models import Review, ReviewFlag


class ReviewSerializer(serializers.ModelSerializer):
    customer = UserPublicSerializer(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id", "event", "customer", "rating", "title", "comment",
            "moderation_status", "host_response", "host_responded_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "customer", "moderation_status", "host_response",
            "host_responded_at", "created_at", "updated_at",
        ]


class ReviewModerationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "moderation_status", "moderation_note"]
        read_only_fields = ["id"]


class HostResponseSerializer(serializers.Serializer):
    host_response = serializers.CharField()


class ReviewFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewFlag
        fields = ["id", "review", "reason", "created_at"]
        read_only_fields = ["id", "created_at"]
