from django.contrib import admin

from coupons.models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "event", "discount_type", "discount_value", "times_used", "max_uses", "is_active"]
    list_filter = ["discount_type", "is_active"]
    search_fields = ["code", "event__title", "created_by__email"]
    readonly_fields = ["id", "times_used", "created_at"]
