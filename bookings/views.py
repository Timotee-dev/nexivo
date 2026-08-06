from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from bookings.serializers import BookingCancelSerializer, BookingSerializer, CheckoutSerializer
from bookings.services import cancel_booking, create_booking
from core.permissions import IsSuperAdmin


class CheckoutView(APIView):
    """
    POST /api/v1/bookings/checkout/
    Supports both authenticated users and guest checkout.
    Guest checkout: pass guest_first_name, guest_last_name, guest_email.
    """

    permission_classes = []  # Allow unauthenticated for guest checkout

    def post(self, request):
        # Handle guest checkout
        guest_email = request.data.get('guest_email', '').strip()
        guest_first_name = request.data.get('guest_first_name', '').strip()
        guest_last_name = request.data.get('guest_last_name', '').strip()

        if not request.user.is_authenticated:
            if not guest_email or not guest_first_name or not guest_last_name:
                return Response(
                    {"detail": "Please sign in or provide your name and email to continue."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            # Get or create guest user
            from accounts.models import User
            import secrets
            user, created = User.objects.get_or_create(
                email=guest_email,
                defaults={
                    'first_name': guest_first_name,
                    'last_name': guest_last_name,
                    'username': guest_email.split('@')[0] + '_' + secrets.token_hex(4),
                    'role': 'customer',
                }
            )
            if not created:
                user.first_name = user.first_name or guest_first_name
                user.last_name = user.last_name or guest_last_name
                user.save(update_fields=['first_name', 'last_name'])
        else:
            user = request.user

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            booking = create_booking(
                customer=user,
                event_id=data["event_id"],
                items=data["items"],
                coupon_code=data.get("coupon_code") or None,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages if hasattr(exc, "messages") else str(exc))

        from payments.services import initialize_payment
        payment_init = initialize_payment(
            booking=booking,
            gateway=data["gateway"],
        )

        return Response(
            {
                "booking": BookingSerializer(booking).data,
                "payment": payment_init,
            },
            status=status.HTTP_201_CREATED,
        )


class MyBookingsView(generics.ListAPIView):
    """GET /api/v1/bookings/mine/ — the authenticated customer's booking history."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Booking.objects.filter(customer=self.request.user)
            .select_related("event")
            .prefetch_related("items__ticket_type")
            .order_by("-created_at")
        )


class BookingDetailView(generics.RetrieveAPIView):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "booking_reference"

    def get_queryset(self):
        if self.request.user.is_super_admin:
            return Booking.objects.all()
        return Booking.objects.filter(customer=self.request.user)


class CancelBookingView(APIView):
    """POST /api/v1/bookings/<reference>/cancel/ — customer or super admin cancels a booking."""

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_reference):
        booking = generics.get_object_or_404(Booking, booking_reference=booking_reference)
        if booking.customer != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You do not own this booking.")

        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            return Response(
                {"detail": f"Cannot cancel a booking with status '{booking.status}'."}, status=400
            )

        serializer = BookingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = cancel_booking(booking, reason=serializer.validated_data.get("reason", ""))
        return Response(BookingSerializer(booking).data)


class HostEventBookingsView(generics.ListAPIView):
    """GET /api/v1/bookings/event/<event_id>/ — host views all bookings/attendees for their event."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from events.models import Event
        event = generics.get_object_or_404(Event, pk=self.kwargs["event_id"])
        if event.host != self.request.user and not self.request.user.is_super_admin:
            raise PermissionDenied("You do not own this event.")
        return (
            Booking.objects.filter(event=event)
            .select_related("customer")
            .prefetch_related("items__ticket_type")
            .order_by("-created_at")
        )


class AllBookingsAdminView(generics.ListAPIView):
    """GET /api/v1/bookings/admin/all/ — super-admin view of every booking platform-wide."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return Booking.objects.select_related("event", "customer").order_by("-created_at")