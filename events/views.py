from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Q, When
from django.utils import timezone
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AuditLog
from core.permissions import IsHostOrSuperAdmin, IsOwnerOrSuperAdmin, IsVerifiedHost, ReadOnlyOrSuperAdmin
from events.filters import EventFilter
from events.geo import nearby_event_ids
from events.models import Category, Event, EventGallery, TicketType
from events.serializers import (
    CategorySerializer,
    EventCreateSerializer,
    EventDetailSerializer,
    EventGallerySerializer,
    EventListSerializer,
    EventModerationSerializer,
    TicketTypeSerializer,
)


class CategoryListCreateView(generics.ListCreateAPIView):
    """GET (public, active only) / POST (super admin only) categories."""

    serializer_class = CategorySerializer
    permission_classes = [ReadOnlyOrSuperAdmin]

    def get_queryset(self):
        qs = Category.objects.annotate(event_count=Count("events"))
        if not (self.request.user.is_authenticated and self.request.user.is_super_admin):
            qs = qs.filter(is_active=True)
        return qs


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.annotate(event_count=Count("events"))
    serializer_class = CategorySerializer
    permission_classes = [ReadOnlyOrSuperAdmin]
    lookup_field = "slug"


class EventListView(generics.ListAPIView):
    """
    GET /api/v1/events/
    Public search & browse endpoint. Supports filtering (events.filters.EventFilter),
    free-text search (?search=), and ordering (?ordering=-start_datetime,price).
    Only published, non-past events are shown to the public; hosts see their own
    drafts via /events/mine/, super admin sees everything via ?status=.
    """

    serializer_class = EventListSerializer
    permission_classes = [AllowAny]
    filterset_class = EventFilter
    search_fields = ["title", "short_description", "description", "venue_name", "city"]
    ordering_fields = ["start_datetime", "created_at", "tickets_sold_count", "average_rating"]
    ordering = ["start_datetime"]

    def get_queryset(self):
        qs = Event.objects.select_related("host", "category").prefetch_related("ticket_types")

        user = self.request.user
        if user.is_authenticated and user.is_super_admin and self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        else:
            qs = qs.filter(status=Event.Status.PUBLISHED, end_datetime__gte=timezone.now())

        return qs


class TrendingEventsView(generics.ListAPIView):
    """GET /api/v1/events/trending/ — ranked by recent ticket sales velocity."""

    serializer_class = EventListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            Event.objects.filter(status=Event.Status.PUBLISHED, end_datetime__gte=timezone.now())
            .select_related("host", "category")
            .prefetch_related("ticket_types")
            .order_by("-tickets_sold_count", "-view_count")[:20]
        )


class UpcomingEventsView(generics.ListAPIView):
    """GET /api/v1/events/upcoming/ — soonest-starting published events."""

    serializer_class = EventListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            Event.objects.filter(status=Event.Status.PUBLISHED, start_datetime__gte=timezone.now())
            .select_related("host", "category")
            .prefetch_related("ticket_types")
            .order_by("start_datetime")[:20]
        )


class FeaturedEventsView(generics.ListAPIView):
    """GET /api/v1/events/featured/ — super-admin-curated featured events."""

    serializer_class = EventListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return (
            Event.objects.filter(
                status=Event.Status.PUBLISHED, is_featured=True,
            )
            .filter(Q(featured_until__isnull=True) | Q(featured_until__gte=now))
            .select_related("host", "category")
            .prefetch_related("ticket_types")
            .order_by("-created_at")
        )


class NearbyEventsView(APIView):
    """
    GET /api/v1/events/nearby/?lat=&lng=&radius_km=50
    Returns published physical/hybrid events within radius_km of the given point,
    sorted by distance ascending.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        if not lat or not lng:
            return Response(
                {"detail": "lat and lng query parameters are required."}, status=400
            )

        try:
            radius_km = float(request.query_params.get("radius_km", 50))
        except ValueError:
            radius_km = 50

        base_qs = Event.objects.filter(
            status=Event.Status.PUBLISHED,
            end_datetime__gte=timezone.now(),
            event_type__in=[Event.EventType.PHYSICAL, Event.EventType.HYBRID],
        ).select_related("host", "category").prefetch_related("ticket_types")

        try:
            ranked = nearby_event_ids(base_qs, lat, lng, radius_km)
        except (TypeError, ValueError):
            return Response({"detail": "lat/lng must be valid decimal coordinates."}, status=400)

        distance_by_id = dict(ranked)
        events = {e.id: e for e in base_qs.filter(id__in=distance_by_id.keys())}

        ordered_events = []
        for event_id, distance in ranked:
            event = events.get(event_id)
            if event:
                event.distance_km = distance
                ordered_events.append(event)

        serializer = EventListSerializer(ordered_events, many=True, context={"request": request})
        return Response(serializer.data)


class RecommendedEventsView(generics.ListAPIView):
    """
    GET /api/v1/events/recommended/
    For authenticated customers: ranks events by matches against the
    customer's preferred categories and followed hosts. Falls back to
    trending events for anonymous users or customers with no preferences set.
    """

    serializer_class = EventListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        base = (
            Event.objects.filter(status=Event.Status.PUBLISHED, end_datetime__gte=timezone.now())
            .select_related("host", "category")
            .prefetch_related("ticket_types")
        )

        user = self.request.user
        profile = getattr(user, "customer_profile", None) if user.is_authenticated else None
        if not profile:
            return base.order_by("-tickets_sold_count")[:20]

        preferred_category_ids = list(profile.preferred_categories.values_list("id", flat=True))
        followed_host_ids = list(profile.followed_hosts.values_list("id", flat=True))

        if not preferred_category_ids and not followed_host_ids:
            return base.order_by("-tickets_sold_count")[:20]

        return (
            base.annotate(
                relevance=Case(
                    When(category_id__in=preferred_category_ids, host_id__in=followed_host_ids, then=2),
                    When(Q(category_id__in=preferred_category_ids) | Q(host_id__in=followed_host_ids), then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            )
            .order_by("-relevance", "start_datetime")[:20]
        )


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET (public, increments view_count) / PATCH / DELETE (owner host or super admin)
    /api/v1/events/<slug>/
    """

    queryset = Event.objects.select_related("host", "category").prefetch_related(
        "ticket_types", "gallery_images"
    )
    lookup_field = "slug"
    owner_field = "host"

    def get_serializer_class(self):
        return EventDetailSerializer

    def get_permissions(self):
        if self.request.method in ("GET",):
            return [AllowAny()]
        return [IsAuthenticated(), IsOwnerOrSuperAdmin()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Event.objects.filter(pk=instance.pk).update(view_count=F("view_count") + 1)
        instance.refresh_from_db(fields=["view_count"])
        serializer = self.get_serializer(instance, context={"request": request})
        return Response(serializer.data)

    def perform_destroy(self, instance):
        AuditLog.objects.create(
            actor=self.request.user, action=AuditLog.Action.EVENT_DELETED,
            target_model="Event", target_id=str(instance.id),
            metadata={"title": instance.title},
        )
        instance.delete()


class MyEventsView(generics.ListCreateAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    """
    GET /api/v1/events/mine/ — host's own events, any status.
    POST /api/v1/events/mine/ — create a new event (host must be verified to
    attach paid ticket types; free-only events are allowed before verification).
    """

    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]
    filterset_class = EventFilter

    def get_serializer_class(self):
        return EventCreateSerializer if self.request.method == "POST" else EventListSerializer

    def get_queryset(self):
        return (
            Event.objects.filter(host=self.request.user)
            .select_related("category")
            .prefetch_related("ticket_types")
            .order_by("-created_at")
        )

    @transaction.atomic
    def perform_create(self, serializer):
        ticket_types_data = serializer.validated_data.get("ticket_types", [])
        has_paid_tickets = any(not tt.get("is_free") and tt.get("price", 0) > 0 for tt in ticket_types_data)

        if has_paid_tickets:
            profile = getattr(self.request.user, "host_profile", None)
            if not (profile and profile.can_sell_paid_tickets):
                raise PermissionDenied(
                    "You must complete NIN and bank verification before creating paid ticket types."
                )

        event = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user, action=AuditLog.Action.EVENT_CREATED,
            target_model="Event", target_id=str(event.id), metadata={"title": event.title},
        )


class EventPublishView(APIView):
    """POST /api/v1/events/<slug>/publish/ — host publishes a draft event."""

    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        event = generics.get_object_or_404(Event, slug=slug)
        if event.host != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You do not own this event.")
        if event.status not in (Event.Status.DRAFT, Event.Status.PENDING_REVIEW):
            return Response({"detail": f"Cannot publish an event with status '{event.status}'."}, status=400)
        if not event.ticket_types.exists():
            return Response({"detail": "Add at least one ticket type before publishing."}, status=400)

        event.publish()
        return Response(EventDetailSerializer(event, context={"request": request}).data)


class EventModerationView(generics.UpdateAPIView):
    """PATCH /api/v1/events/<slug>/moderate/ — super-admin-only suspend/feature toggle."""

    queryset = Event.objects.all()
    serializer_class = EventModerationSerializer
    lookup_field = "slug"

    def get_permissions(self):
        from core.permissions import IsSuperAdmin
        return [IsAuthenticated(), IsSuperAdmin()]

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        event = serializer.save()
        if event.status != old_status:
            AuditLog.objects.create(
                actor=self.request.user, action=AuditLog.Action.EVENT_DELETED
                if event.status == Event.Status.CANCELLED else AuditLog.Action.SETTINGS_CHANGED,
                target_model="Event", target_id=str(event.id),
                metadata={"old_status": old_status, "new_status": event.status},
            )


class TicketTypeListCreateView(generics.ListCreateAPIView):
    """
    GET (public) / POST (event owner host, must be verified for paid types)
    /api/v1/events/<slug>/ticket-types/
    """

    serializer_class = TicketTypeSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def get_event(self):
        return generics.get_object_or_404(Event, slug=self.kwargs["slug"])

    def get_queryset(self):
        return self.get_event().ticket_types.all().order_by("display_order", "price")

    def perform_create(self, serializer):
        event = self.get_event()
        if event.host != self.request.user and not self.request.user.is_super_admin:
            raise PermissionDenied("You do not own this event.")

        is_paid = not serializer.validated_data.get("is_free") and serializer.validated_data.get("price", 0) > 0
        if is_paid:
            profile = getattr(self.request.user, "host_profile", None)
            if not (profile and profile.can_sell_paid_tickets):
                raise PermissionDenied(
                    "You must complete NIN and bank verification before adding paid ticket types."
                )

        serializer.save(event=event, quantity_remaining=serializer.validated_data["quantity_total"])


class TicketTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TicketTypeSerializer
    permission_classes = [IsAuthenticated]
    queryset = TicketType.objects.select_related("event")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if obj.event.host != request.user and not request.user.is_super_admin:
            raise PermissionDenied("You do not own this event.")


class EventGalleryView(generics.ListCreateAPIView):
    """GET (public) / POST (event owner) /api/v1/events/<slug>/gallery/"""

    serializer_class = EventGallerySerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def get_event(self):
        return generics.get_object_or_404(Event, slug=self.kwargs["slug"])

    def get_queryset(self):
        return self.get_event().gallery_images.all()

    def perform_create(self, serializer):
        event = self.get_event()
        if event.host != self.request.user and not self.request.user.is_super_admin:
            raise PermissionDenied("You do not own this event.")
        serializer.save(event=event)


class ToggleFavoriteView(APIView):
    """POST /api/v1/events/<slug>/favorite/ — toggles favorite for the authenticated customer."""

    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        event = generics.get_object_or_404(Event, slug=slug)
        profile = getattr(request.user, "customer_profile", None)
        if not profile:
            return Response({"detail": "Only customers can favorite events."}, status=403)

        if profile.favorite_events.filter(pk=event.pk).exists():
            profile.favorite_events.remove(event)
            Event.objects.filter(pk=event.pk).update(favorite_count=F("favorite_count") - 1)
            favorited = False
        else:
            profile.favorite_events.add(event)
            Event.objects.filter(pk=event.pk).update(favorite_count=F("favorite_count") + 1)
            favorited = True

        return Response({"favorited": favorited})