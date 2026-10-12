from django.contrib import admin

from bookings.models import Booking, BookingItem


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0
    readonly_fields = ["line_total"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["booking_reference", "customer", "event", "status", "total_amount", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["booking_reference", "customer__email", "event__title"]
    readonly_fields = ["id", "booking_reference", "created_at", "updated_at"]
    inlines = [BookingItemInline]
