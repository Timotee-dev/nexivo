from django.urls import path

from notifications.views import (
    MarkAllReadView,
    MarkNotificationReadView,
    MyNotificationsView,
    NotificationPreferenceView,
)

app_name = "notifications"

urlpatterns = [
    path("mine/", MyNotificationsView.as_view(), name="my_notifications"),
    path("mark-all-read/", MarkAllReadView.as_view(), name="mark_all_read"),
    path("<uuid:notification_id>/read/", MarkNotificationReadView.as_view(), name="mark_read"),
    path("preferences/", NotificationPreferenceView.as_view(), name="preferences"),
]
