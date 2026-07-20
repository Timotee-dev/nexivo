from django.contrib import admin

from notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "channel", "event_type", "status", "created_at"]
    list_filter = ["channel", "event_type", "status"]
    search_fields = ["recipient__email"]
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "email_enabled", "whatsapp_enabled", "marketing_emails_enabled"]
