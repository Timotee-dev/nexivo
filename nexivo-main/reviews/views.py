from django.db import transaction
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsSuperAdmin
from events.models import Event
from reviews.models import Review, ReviewFlag
from reviews.serializers import (
    HostResponseSerializer,
    ReviewFlagSerializer,
    ReviewModerationSerializer,
    ReviewSerializer,
)
from reviews.services import customer_has_eligible_ticket, recalculate_event_rating


class EventReviewsView(generics.ListCreateAPIView):
    """GET (public, approved only) / POST (customer with an eligible ticket) /api/v1/reviews/event/<event_id>/"""

    serializer_class = ReviewSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def get_event(self):
        return generics.get_object_or_404(Event, pk=self.kwargs["event_id"])

    def get_queryset(self):
        event = self.get_event()
        qs = event.reviews.select_related("customer")
        if not (self.request.user.is_authenticated and self.request.user.is_super_admin):
            qs = qs.filter(moderation_status=Review.ModerationStatus.APPROVED)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        event = self.get_event()
        if not self.request.user.is_customer:
            raise PermissionDenied("Only customers can leave reviews.")
        if not customer_has_eligible_ticket(self.request.user, event):
            raise PermissionDenied("You can only review events you've purchased a ticket for.")
        if Review.objects.filter(event=event, customer=self.request.user).exists():
            raise ValidationError("You've already reviewed this event.")

        review = serializer.save(event=event, customer=self.request.user)
        recalculate_event_rating(event)
        return review


class MyReviewsView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Review.objects.filter(customer=self.request.user).select_related("event")


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]
    queryset = Review.objects.select_related("event", "customer")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if obj.customer != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You do not own this review.")

    def perform_update(self, serializer):
        review = serializer.save()
        recalculate_event_rating(review.event)

    def perform_destroy(self, instance):
        event = instance.event
        instance.delete()
        recalculate_event_rating(event)


class HostRespondToReviewView(APIView):
    """POST /api/v1/reviews/<review_id>/respond/ — event host replies publicly to a review."""

    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
        from django.utils import timezone
        review = generics.get_object_or_404(Review, pk=review_id)
        if review.event.host != request.user and not request.user.is_super_admin:
            raise PermissionDenied("Only the event host can respond to this review.")

        serializer = HostResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review.host_response = serializer.validated_data["host_response"]
        review.host_responded_at = timezone.now()
        review.save(update_fields=["host_response", "host_responded_at"])
        return Response(ReviewSerializer(review).data)


class FlagReviewView(APIView):
    """POST /api/v1/reviews/<review_id>/flag/ — flag a review for moderator attention."""

    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
        review = generics.get_object_or_404(Review, pk=review_id)
        serializer = ReviewFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        flag, created = ReviewFlag.objects.get_or_create(
            review=review, flagged_by=request.user,
            defaults={"reason": serializer.validated_data["reason"]},
        )
        if created:
            review.flagged_count += 1
            if review.flagged_count >= 3 and review.moderation_status == Review.ModerationStatus.APPROVED:
                review.moderation_status = Review.ModerationStatus.FLAGGED
            review.save(update_fields=["flagged_count", "moderation_status"])

        return Response(ReviewFlagSerializer(flag).data, status=201 if created else 200)


class AdminModerateReviewView(generics.UpdateAPIView):
    """PATCH /api/v1/reviews/admin/<review_id>/moderate/ — super admin approves/rejects a flagged review."""

    queryset = Review.objects.all()
    serializer_class = ReviewModerationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def perform_update(self, serializer):
        review = serializer.save(moderated_by=self.request.user)
        recalculate_event_rating(review.event)


class AdminFlaggedReviewsView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = Review.objects.filter(moderation_status=Review.ModerationStatus.FLAGGED).select_related("event", "customer")
