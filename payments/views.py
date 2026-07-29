import json

from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsSuperAdmin
from payments.models import Payment, ReconciliationRecord, Refund, WebhookEvent
from payments.serializers import (
    PaymentSerializer,
    ReconciliationRecordSerializer,
    RefundDecisionSerializer,
    RefundRequestSerializer,
    RefundSerializer,
    VerifyPaymentSerializer,
    WebhookEventSerializer,
)
from payments.services import process_webhook, request_refund, verify_and_finalize_payment


class MyPaymentsView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payment.objects.filter(customer=self.request.user).select_related("booking").order_by("-created_at")


class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "gateway_reference"

    def get_queryset(self):
        if self.request.user.is_super_admin:
            return Payment.objects.all()
        return Payment.objects.filter(customer=self.request.user)


class VerifyPaymentView(APIView):
    """
    POST /api/v1/payments/verify/
    Polling fallback for the checkout UI: explicitly asks us to re-check a
    payment's status with the gateway (useful if the webhook hasn't arrived
    yet by the time the customer returns from the gateway's hosted page).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = generics.get_object_or_404(Payment, gateway_reference=serializer.validated_data["reference"])
        if payment.customer != request.user and not request.user.is_super_admin:
            raise PermissionDenied("This payment does not belong to you.")

        payment = verify_and_finalize_payment(payment)
        return Response(PaymentSerializer(payment).data)


class WebhookView(APIView):
    """
    POST /api/v1/payments/webhook/<gateway>/
    Public (no auth — gateways can't authenticate as a Nexivo user), but
    every request's signature is cryptographically verified before any
    processing happens. Always returns 200 quickly once recorded, per
    gateway best practice, even if processing fails internally (recorded
    failures are retried via the WebhookEvent retry/reprocess path instead
    of relying on the gateway's own redelivery, which has its own backoff).
    """

    permission_classes = [AllowAny]

    def post(self, request, gateway):
        if gateway not in Payment.Gateway.values:
            return Response({"detail": "Unknown gateway."}, status=404)

        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except json.JSONDecodeError:
            return Response({"detail": "Invalid JSON payload."}, status=400)

        result = process_webhook(
            gateway=gateway, payload=payload, headers=dict(request.headers), raw_body=request.body,
        )

        # Always 200 for recognized, signature-valid webhooks so the gateway
        # doesn't endlessly retry; rejected-signature requests get 400.
        http_status = 400 if result["status"] == "rejected" else 200
        return Response(result, status=http_status)


class RequestRefundView(APIView):
    """POST /api/v1/payments/<reference>/refund/ — customer requests a refund."""

    permission_classes = [IsAuthenticated]

    def post(self, request, gateway_reference):
        payment = generics.get_object_or_404(Payment, gateway_reference=gateway_reference)
        if payment.customer != request.user and not request.user.is_super_admin:
            raise PermissionDenied("This payment does not belong to you.")
        if payment.status != Payment.Status.SUCCESSFUL:
            return Response({"detail": "Only successful payments can be refunded."}, status=400)

        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refund = request_refund(
            payment=payment, requested_by=request.user,
            amount=serializer.validated_data.get("amount"),
            reason=serializer.validated_data["reason"],
        )
        return Response(RefundSerializer(refund).data, status=201)


class RefundDecisionView(APIView):
    """
    POST /api/v1/payments/refunds/<refund_id>/decide/
    Host (for their own event's bookings) or super admin approves/rejects.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, refund_id):
        refund = generics.get_object_or_404(Refund, pk=refund_id)
        event_host = refund.payment.booking.event.host
        if event_host != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You are not authorized to decide on this refund.")

        serializer = RefundDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["approve"]:
            from payments.models import Refund
            refund.status = Refund.Status.APPROVED
            refund.approved_by = request.user
            refund.save(update_fields=["status", "approved_by"])
        else:
            refund.status = Refund.Status.REJECTED
            refund.rejection_reason = serializer.validated_data.get("rejection_reason", "")
            refund.save(update_fields=["status", "rejection_reason"])

        return Response(RefundSerializer(refund).data)


class MyRefundsView(generics.ListAPIView):
    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.filter(requested_by=self.request.user).select_related("payment")


class HostRefundsView(generics.ListAPIView):
    """GET /api/v1/payments/refunds/pending/ — refunds awaiting host decision."""

    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Refund.objects.filter(status=Refund.Status.REQUESTED).select_related(
            "payment", "payment__booking", "payment__booking__event"
        )
        if self.request.user.is_super_admin:
            return qs
        return qs.filter(payment__booking__event__host=self.request.user)


class AdminAllPaymentsView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return Payment.objects.select_related("booking", "customer").order_by("-created_at")


class AdminFlaggedPaymentsView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return Payment.objects.filter(flagged_for_review=True).select_related("booking", "customer")


class AdminWebhookEventsView(generics.ListAPIView):
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = WebhookEvent.objects.all()


class AdminReconciliationView(generics.ListAPIView):
    serializer_class = ReconciliationRecordSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = ReconciliationRecord.objects.select_related("payment")


class TriggerReconciliationView(APIView):
    """POST /api/v1/payments/admin/reconcile/ — manually trigger reconciliation (normally cron-driven)."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        from payments.reconciliation import reconcile_all_gateways
        results = reconcile_all_gateways()
        return Response({"results": results})