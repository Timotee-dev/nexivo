from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHostOrSuperAdmin, IsSuperAdmin
from payouts.models import Payout, PayoutLedgerEntry
from payouts.serializers import (
    HoldPayoutSerializer,
    HostBalanceSerializer,
    PayoutLedgerEntrySerializer,
    PayoutSerializer,
)
from payouts.services import get_host_balance, hold_payout, release_held_payout


class MyPayoutsView(generics.ListAPIView):
    """GET /api/v1/payouts/mine/ — host's own payout history."""

    serializer_class = PayoutSerializer
    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]

    def get_queryset(self):
        return Payout.objects.filter(host=self.request.user).prefetch_related("payments")


class MyBalanceView(APIView):
    """GET /api/v1/payouts/balance/ — host's current unpaid earnings balance."""

    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]

    def get(self, request):
        balance = get_host_balance(request.user)
        return Response(HostBalanceSerializer({"host_id": request.user.id, "balance": balance}).data)


class MyLedgerView(generics.ListAPIView):
    """GET /api/v1/payouts/ledger/ — host's full earnings ledger history."""

    serializer_class = PayoutLedgerEntrySerializer
    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]

    def get_queryset(self):
        return PayoutLedgerEntry.objects.filter(host=self.request.user).select_related(
            "related_payment", "related_payout"
        )


class AdminAllPayoutsView(generics.ListAPIView):
    serializer_class = PayoutSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = Payout.objects.select_related("host").prefetch_related("payments")


class AdminHoldPayoutView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, payout_id):
        payout = generics.get_object_or_404(Payout, pk=payout_id)
        serializer = HoldPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payout = hold_payout(payout, held_by=request.user, reason=serializer.validated_data["reason"])
        return Response(PayoutSerializer(payout).data)


class AdminReleasePayoutView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, payout_id):
        payout = generics.get_object_or_404(Payout, pk=payout_id)
        payout = release_held_payout(payout)
        return Response(PayoutSerializer(payout).data)


class AdminTriggerPayoutsView(APIView):
    """POST /api/v1/payouts/admin/run/ — manually trigger the payout scheduling job."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        from payouts.services import schedule_due_payouts
        scheduled = schedule_due_payouts()
        return Response({"payouts_scheduled": len(scheduled), "payouts": PayoutSerializer(scheduled, many=True).data})
