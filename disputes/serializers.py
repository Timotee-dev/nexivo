from rest_framework import serializers
from accounts.serializers import UserPublicSerializer
from disputes.models import Dispute, DisputeMessage


class DisputeMessageSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)

    class Meta:
        model = DisputeMessage
        fields = ["id", "author", "body", "attachment", "is_internal", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class DisputeSerializer(serializers.ModelSerializer):
    raised_by = UserPublicSerializer(read_only=True)
    messages = DisputeMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "reference", "raised_by", "against_host", "booking", "payment",
            "category", "status", "resolution", "subject", "description",
            "resolution_notes", "resolved_at", "messages", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "raised_by", "status", "resolution",
            "resolution_notes", "resolved_at", "created_at", "updated_at",
        ]


class DisputeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ["booking", "payment", "category", "subject", "description"]


class DisputeResolveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        Dispute.Status.RESOLVED_CUSTOMER, Dispute.Status.RESOLVED_HOST, Dispute.Status.CLOSED,
    ])
    resolution = serializers.ChoiceField(choices=Dispute.Resolution.choices, required=False)
    resolution_notes = serializers.CharField(required=False, allow_blank=True)


class AddMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisputeMessage
        fields = ["body", "attachment", "is_internal"]
