from django.contrib import admin

from core.models import Announcement, PlatformFee, PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ["platform_name", "platform_commission_percent", "maintenance_mode", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        # Singleton: block creation once a row exists.
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from core.models import PlatformFee
        super().save_model(request, obj, form, change)
        PlatformFee.objects.create(
            platform_commission_percent=obj.platform_commission_percent,
            payment_processing_fee_percent=obj.payment_processing_fee_percent,
            payment_processing_fee_fixed=obj.payment_processing_fee_fixed,
        )


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "audience", "is_active", "starts_at", "ends_at", "created_at"]
    list_filter = ["audience", "is_active"]
    search_fields = ["title", "message"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PlatformFee)
class PlatformFeeAdmin(admin.ModelAdmin):
    list_display = ["platform_commission_percent", "payment_processing_fee_percent", "effective_from"]
    readonly_fields = [f.name for f in PlatformFee._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
