from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification, NotificationPreference
from notifications.serializers import NotificationPreferenceSerializer, NotificationSerializer


class MyNotificationsView(generics.ListAPIView):
    """GET /api/v1/notifications/mine/ — in-app notification feed."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user, channel=Notification.Channel.IN_APP
        )


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        notification = generics.get_object_or_404(
            Notification, pk=notification_id, recipient=request.user
        )
        notification.read_at = timezone.now()
        notification.status = Notification.Status.READ
        notification.save(update_fields=["read_at", "status"])
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, channel=Notification.Channel.IN_APP, read_at__isnull=True
        ).update(read_at=timezone.now(), status=Notification.Status.READ)
        return Response({"marked_read": updated})


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        pref, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return pref
