from django.contrib import admin

from reviews.models import Review, ReviewFlag


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["event", "customer", "rating", "moderation_status", "flagged_count", "created_at"]
    list_filter = ["moderation_status", "rating"]
    search_fields = ["event__title", "customer__email", "comment"]
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        from reviews.services import recalculate_event_rating
        updated = queryset.update(moderation_status=Review.ModerationStatus.APPROVED, moderated_by=request.user)
        for review in queryset:
            recalculate_event_rating(review.event)
        self.message_user(request, f"{updated} review(s) approved.")

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        from reviews.services import recalculate_event_rating
        updated = queryset.update(moderation_status=Review.ModerationStatus.REJECTED, moderated_by=request.user)
        for review in queryset:
            recalculate_event_rating(review.event)
        self.message_user(request, f"{updated} review(s) rejected.")


@admin.register(ReviewFlag)
class ReviewFlagAdmin(admin.ModelAdmin):
    list_display = ["review", "flagged_by", "reason", "created_at"]
    search_fields = ["review__event__title"]
