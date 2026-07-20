from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsSuperAdmin
from disputes.models import Dispute, DisputeMessage
from disputes.serializers import (
    AddMessageSerializer, DisputeCreateSerializer,
    DisputeResolveSerializer, DisputeSerializer,
)


class MyDisputesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return DisputeCreateSerializer if self.request.method == "POST" else DisputeSerializer

    def get_queryset(self):
        return Dispute.objects.filter(raised_by=self.request.user).select_related("against_host", "booking").prefetch_related("messages")

    def perform_create(self, serializer):
        booking = serializer.validated_data.get("booking")
        if booking and booking.customer != self.request.user:
            raise PermissionDenied("This booking does not belong to you.")
        host = booking.event.host if booking else None
        if not host:
            raise PermissionDenied("Cannot determine host for this dispute.")
        dispute = serializer.save(raised_by=self.request.user, against_host=host)
        DisputeMessage.objects.create(dispute=dispute, author=self.request.user, body=dispute.description)


class DisputeDetailView(generics.RetrieveAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_super_admin:
            return Dispute.objects.all()
        return Dispute.objects.filter(raised_by=self.request.user)


class AdminAllDisputesView(generics.ListAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = Dispute.objects.select_related("raised_by", "against_host").prefetch_related("messages")
    filterset_fields = ["status", "category"]


class AdminResolveDisputeView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        dispute = generics.get_object_or_404(Dispute, pk=pk)
        serializer = DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dispute.status = serializer.validated_data["status"]
        dispute.resolution = serializer.validated_data.get("resolution", "")
        dispute.resolution_notes = serializer.validated_data.get("resolution_notes", "")
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save()

        # Auto-trigger refund if resolution is full/partial refund
        if dispute.resolution in (Dispute.Resolution.FULL_REFUND, Dispute.Resolution.PARTIAL_REFUND) and dispute.payment:
            from payments.services import approve_refund, request_refund
            refund = request_refund(
                payment=dispute.payment, requested_by=request.user,
                reason=f"Dispute {dispute.reference} resolved: {dispute.resolution}"
            )
            approve_refund(refund=refund, approved_by=request.user)

        return Response(DisputeSerializer(dispute).data)


class AddDisputeMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        dispute = generics.get_object_or_404(Dispute, pk=pk)
        # Customer, host, or super admin can message
        if not (dispute.raised_by == request.user or
                dispute.against_host == request.user or
                request.user.is_super_admin):
            raise PermissionDenied("You are not a party to this dispute.")

        serializer = AddMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Only super admin can post internal notes
        is_internal = serializer.validated_data.get("is_internal", False) and request.user.is_super_admin
        msg = DisputeMessage.objects.create(
            dispute=dispute, author=request.user,
            body=serializer.validated_data["body"],
            attachment=serializer.validated_data.get("attachment"),
            is_internal=is_internal,
        )
        if dispute.status == Dispute.Status.OPEN:
            dispute.status = Dispute.Status.UNDER_REVIEW
            dispute.save(update_fields=["status"])

        return Response(AddMessageSerializer(msg).data, status=201)
