from django.urls import path
from analytics.views import (
    EventAnalyticsView, ExportBookingsCSVView,
    HostDashboardView, PlatformDashboardView,
)

app_name = "analytics"

urlpatterns = [
    path("host/", HostDashboardView.as_view(), name="host_dashboard"),
    path("platform/", PlatformDashboardView.as_view(), name="platform_dashboard"),
    path("event/<uuid:event_id>/", EventAnalyticsView.as_view(), name="event_analytics"),
    path("event/<uuid:event_id>/export/csv/", ExportBookingsCSVView.as_view(), name="export_csv"),
]
