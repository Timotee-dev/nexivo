from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHostOrSuperAdmin, IsSuperAdmin
from events.models import Event


class HostDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsHostOrSuperAdmin]

    def get(self, request):
        from analytics.services import host_dashboard
        return Response(host_dashboard(request.user))


class EventAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        from analytics.services import event_analytics
        event = Event.objects.get(pk=event_id)
        if event.host != request.user and not request.user.is_super_admin:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not own this event.")
        return Response(event_analytics(event))


class PlatformDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        from analytics.services import platform_dashboard
        return Response(platform_dashboard())


class ExportBookingsCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        from analytics.services import export_bookings_csv
        event = Event.objects.get(pk=event_id)
        if event.host != request.user and not request.user.is_super_admin:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not own this event.")
        csv_data = export_bookings_csv(event)
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="bookings-{event.slug}.csv"'
        return response
