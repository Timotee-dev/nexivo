from rest_framework import serializers

from payments.models import Payment, Refund, ReconciliationRecord, WebhookEvent


class PaymentSerializer(serializers.ModelSerializer):
    booking_reference = serializers.CharField(source="booking.booking_reference", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "booking", "booking_reference", "gateway", "gateway_reference",
            "gateway_transaction_id", "status", "amount", "currency",
            "platform_commission_percent", "platform_commission_amount",
            "host_payout_amount", "checkout_url", "invoice_pdf", "paid_at", "failed_reason",
            "risk_score", "flagged_for_review", "created_at",
        ]
        read_only_fields = fields


class VerifyPaymentSerializer(serializers.Serializer):
    reference = serializers.CharField()


class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    reason = serializers.CharField()


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = [
            "id", "payment", "requested_by", "approved_by", "amount",
            "processing_fee_deducted", "reason", "status", "gateway_refund_id",
            "rejection_reason", "requested_at", "completed_at",
        ]
        read_only_fields = fields


class RefundDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = ["id", "gateway", "event_type", "status", "retry_count", "last_error", "created_at", "processed_at"]
        read_only_fields = fields


class ReconciliationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationRecord
        fields = [
            "id", "gateway", "payment", "gateway_transaction_id", "local_amount",
            "gateway_amount", "discrepancy_type", "notes", "resolved", "run_date", "created_at",
        ]
        read_only_fields = fields
