from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import AuditLog, CustomerProfile, HostProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-created_at"]
    list_display = ["email", "username", "role", "status", "is_staff", "created_at"]
    list_filter = ["role", "status", "is_staff", "email_verified"]
    search_fields = ["email", "username", "phone_number", "first_name", "last_name"]
    readonly_fields = ["id", "created_at", "updated_at", "last_login_ip"]

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "avatar", "bio", "date_of_birth")}),
        ("Role & Status", {"fields": ("role", "status")}),
        ("Verification", {"fields": ("email_verified", "phone_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Security", {"fields": ("last_login_ip", "failed_login_attempts", "locked_until")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "role", "password1", "password2")}),
    )


@admin.register(HostProfile)
class HostProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user", "business_name", "nin_verification_status",
        "bank_details_verified", "can_sell_paid_tickets", "total_revenue",
    ]
    list_filter = ["nin_verification_status", "bank_details_verified", "can_sell_paid_tickets"]
    search_fields = ["user__email", "business_name", "nin_number"]
    readonly_fields = [
        "id", "total_events_created", "total_tickets_sold",
        "total_revenue", "average_rating", "created_at", "updated_at",
    ]
    actions = ["approve_nin", "reject_nin"]

    @admin.action(description="Approve selected hosts' NIN verification")
    def approve_nin(self, request, queryset):
        from django.utils import timezone
        updated = 0
        for profile in queryset:
            profile.nin_verified = True
            profile.nin_verification_status = HostProfile.VerificationStatus.VERIFIED
            profile.nin_verified_at = timezone.now()
            profile.refresh_paid_ticket_eligibility()
            profile.save()
            from notifications.services import notify_host_verification_update
            notify_host_verification_update(profile)
            updated += 1
        self.message_user(request, f"{updated} host(s) NIN-verified.")

    @admin.action(description="Reject selected hosts' NIN verification")
    def reject_nin(self, request, queryset):
        updated = queryset.update(
            nin_verified=False,
            nin_verification_status=HostProfile.VerificationStatus.REJECTED,
        )
        for profile in queryset:
            from notifications.services import notify_host_verification_update
            notify_host_verification_update(profile)
        self.message_user(request, f"{updated} host(s) NIN verification rejected.")


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "city", "country"]
    search_fields = ["user__email", "city"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "target_model", "target_id", "created_at"]
    list_filter = ["action", "target_model"]
    search_fields = ["actor__email", "target_id"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
