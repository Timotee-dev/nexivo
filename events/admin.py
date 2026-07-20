from django.contrib import admin

from events.models import Category, Event, EventGallery, TicketType


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0
    fields = ["name", "price", "is_free", "quantity_total", "quantity_remaining", "is_active"]
    readonly_fields = ["quantity_remaining"]


class EventGalleryInline(admin.TabularInline):
    model = EventGallery
    extra = 0
    fields = ["image", "caption", "display_order"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "display_order"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        "title", "host", "event_type", "status", "city", "start_datetime",
        "is_featured", "tickets_sold_count", "average_rating",
    ]
    list_filter = ["event_type", "status", "is_featured", "country"]
    search_fields = ["title", "host__email", "city", "venue_name"]
    readonly_fields = [
        "id", "slug", "view_count", "tickets_sold_count", "favorite_count",
        "average_rating", "review_count", "published_at", "created_at", "updated_at",
    ]
    inlines = [TicketTypeInline, EventGalleryInline]
    actions = ["suspend_events", "feature_events", "unfeature_events"]

    @admin.action(description="Suspend selected events")
    def suspend_events(self, request, queryset):
        updated = queryset.update(status=Event.Status.SUSPENDED)
        self.message_user(request, f"{updated} event(s) suspended.")

    @admin.action(description="Feature selected events")
    def feature_events(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} event(s) featured.")

    @admin.action(description="Unfeature selected events")
    def unfeature_events(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} event(s) unfeatured.")


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "price", "is_free", "quantity_total", "quantity_remaining", "is_active"]
    list_filter = ["is_free", "is_active", "is_early_bird"]
    search_fields = ["name", "event__title"]
