from django.contrib import admin

from payments.models import Payment, ReconciliationRecord, Refund, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "gateway_reference", "gateway", "status", "amount", "platform_commission_amount",
        "host_payout_amount", "flagged_for_review", "created_at",
    ]
    list_filter = ["gateway", "status", "flagged_for_review"]
    search_fields = ["gateway_reference", "gateway_transaction_id", "customer__email"]
    readonly_fields = [f.name for f in Payment._meta.fields if f.name not in ("flagged_for_review",)]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["payment", "amount", "status", "requested_by", "approved_by", "requested_at"]
    list_filter = ["status"]
    search_fields = ["payment__gateway_reference"]


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["gateway", "event_type", "status", "retry_count", "created_at"]
    list_filter = ["gateway", "status"]
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ReconciliationRecord)
class ReconciliationRecordAdmin(admin.ModelAdmin):
    list_display = ["gateway", "gateway_transaction_id", "discrepancy_type", "resolved", "run_date"]
    list_filter = ["gateway", "discrepancy_type", "resolved"]
    actions = ["mark_resolved"]

    @admin.action(description="Mark selected records as resolved")
    def mark_resolved(self, request, queryset):
        updated = queryset.update(resolved=True)
        self.message_user(request, f"{updated} record(s) marked resolved.")
