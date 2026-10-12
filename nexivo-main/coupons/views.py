from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from coupons.models import Coupon
from coupons.serializers import CouponSerializer, CouponValidateSerializer
from coupons.services import apply_coupon_preview
from core.permissions import IsHostOrSuperAdmin


class CouponListCreateView(generics.ListCreateAPIView):
    """
    GET/POST /api/v1/coupons/
    Hosts see/manage coupons for their own events; super admin sees/manages all,
    including platform-wide coupons (event=null).
    """

    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Coupon.objects.select_related("event", "created_by").order_by("-created_at")
        return Coupon.objects.filter(created_by=user).select_related("event").order_by("-created_at")

    def perform_create(self, serializer):
        event = serializer.validated_data.get("event")
        if event and event.host != self.request.user and not self.request.user.is_super_admin:
            raise PermissionDenied("You can only create coupons for your own events.")
        if not event and not self.request.user.is_super_admin:
            raise PermissionDenied("Only super admin can create platform-wide coupons.")
        serializer.save(created_by=self.request.user)


class CouponDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]
    queryset = Coupon.objects.select_related("event")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if obj.created_by != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You do not own this coupon.")


class ValidateCouponView(APIView):
    """
    POST /api/v1/coupons/validate/
    Lets the checkout UI preview a discount before committing to checkout.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                result = apply_coupon_preview(
                    code=serializer.validated_data["code"],
                    event_id=serializer.validated_data["event_id"],
                    subtotal=serializer.validated_data["subtotal"],
                )
        except DjangoValidationError as exc:
            raise ValidationError(str(exc.message) if hasattr(exc, "message") else exc.messages)

        return Response(result)
