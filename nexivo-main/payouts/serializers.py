from rest_framework import serializers

from payouts.models import Payout, PayoutLedgerEntry


class PayoutSerializer(serializers.ModelSerializer):
    payment_count = serializers.IntegerField(source="payments.count", read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id", "host", "gateway", "amount", "currency", "status",
            "scheduled_for", "completed_at", "gateway_transfer_id",
            "failure_reason", "held_reason", "payment_count", "created_at",
        ]
        read_only_fields = fields


class PayoutLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutLedgerEntry
        fields = ["id", "entry_type", "amount", "related_payment", "related_payout", "note", "created_at"]
        read_only_fields = fields


class HoldPayoutSerializer(serializers.Serializer):
    reason = serializers.CharField()


class HostBalanceSerializer(serializers.Serializer):
    host_id = serializers.UUIDField()
    balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(default="NGN")
