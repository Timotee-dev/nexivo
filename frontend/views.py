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
from payments.services import approve_refund, process_webhook, request_refund, verify_and_finalize_payment


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
            refund = approve_refund(refund=refund, approved_by=request.user)
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


def help_centre(request):
    faqs = [
        {
            "title": "For Attendees",
            "questions": [
                {"q": "How do I buy a ticket?", "a": "Browse events, select your ticket type, and pay securely with Paystack. You'll receive a QR code ticket via email instantly."},
                {"q": "How do I access my tickets?", "a": "Log in to your account and go to Dashboard → My Tickets. Your QR code ticket will be there."},
                {"q": "Can I get a refund?", "a": "Refund policies are set by each event organizer. Check the event page for the specific refund policy before purchasing."},
                {"q": "What if my QR code doesn't scan?", "a": "Show the venue staff your ticket code (visible on your ticket) and they can verify manually."},
                {"q": "Can I transfer my ticket to someone else?", "a": "Yes — go to My Tickets and click Transfer on the ticket you want to send."},
            ]
        },
        {
            "title": "For Event Organisers",
            "questions": [
                {"q": "How do I create an event?", "a": "Register as a host, go to Dashboard → Create Event, fill in your event details and ticket types, then publish."},
                {"q": "When do I get paid?", "a": "95% of ticket sales go directly to your bank account via Paystack. Payouts follow Paystack's standard settlement schedule."},
                {"q": "How does the QR check-in work?", "a": "Share your event check-in link (nexivo.com.ng/checkin/your-event) with your team. Anyone can scan tickets using their phone camera — no app needed."},
                {"q": "Can I set different ticket types?", "a": "Yes — you can create multiple ticket types (VIP, Regular, Early Bird, etc.) with different prices and quantities."},
                {"q": "Is there a fee to use Nexivo?", "a": "Nexivo takes a 5% platform fee per ticket sold. You keep 95% of all revenue."},
            ]
        }
    ]
    return render(request, "frontend/help.html", {"faqs": faqs})


def contact_view(request):
    return render(request, "frontend/contact.html")


def terms_view(request):
    sections = [
        {"title": "Acceptance of Terms", "content": "By accessing and using Nexivo, you accept and agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our platform."},
        {"title": "Use of the Platform", "content": "Nexivo is a marketplace that connects event organizers with attendees. Organizers are responsible for their events, ticket pricing, and refund policies. Nexivo does not own or organize any events listed on the platform."},
        {"title": "Ticket Purchases", "content": "All ticket purchases are final unless the event organizer offers refunds. Nexivo processes payments securely via Paystack. A 5% platform fee is deducted from all ticket sales."},
        {"title": "Organizer Responsibilities", "content": "Event organizers are responsible for delivering the events they advertise. Organizers must provide accurate event information and honor their stated refund policies."},
        {"title": "Prohibited Activities", "content": "You may not use Nexivo to sell fraudulent tickets, misrepresent events, or engage in any activity that violates Nigerian law. Accounts found in violation will be suspended."},
        {"title": "Limitation of Liability", "content": "Nexivo is not liable for any direct, indirect, or consequential damages arising from your use of the platform or attendance at events booked through Nexivo."},
        {"title": "Changes to Terms", "content": "Nexivo reserves the right to modify these terms at any time. Continued use of the platform after changes constitutes acceptance of the new terms."},
    ]
    return render(request, "frontend/terms.html", {"sections": sections})


def privacy_view(request):
    sections = [
        {"title": "Information We Collect", "content": "We collect information you provide when creating an account (name, email, phone number), booking tickets (payment details processed by Paystack), and using our platform (event preferences, booking history)."},
        {"title": "How We Use Your Information", "content": "We use your information to process ticket bookings, send confirmation emails with your QR code tickets, improve our platform, and communicate important updates about your bookings."},
        {"title": "Payment Information", "content": "All payment processing is handled by Paystack. Nexivo does not store your card details. Bank account information for hosts is encrypted and stored securely."},
        {"title": "Information Sharing", "content": "We share your name and contact details with event organizers for events you book. We do not sell your personal information to third parties."},
        {"title": "Data Security", "content": "We use industry-standard encryption to protect your data. All sensitive information is encrypted at rest and in transit."},
        {"title": "Your Rights", "content": "You can access, update, or delete your account information at any time through your dashboard. To request complete data deletion, contact us at privacy@nexivo.com.ng"},
        {"title": "Cookies", "content": "Nexivo uses essential cookies to keep you logged in and remember your preferences. We do not use tracking cookies for advertising."},
    ]
    return render(request, "frontend/privacy.html", {"sections": sections})