from django.contrib import admin

from payouts.models import Payout, PayoutLedgerEntry


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["host", "gateway", "amount", "status", "scheduled_for", "completed_at"]
    list_filter = ["gateway", "status"]
    search_fields = ["host__email"]
    filter_horizontal = ["payments"]


@admin.register(PayoutLedgerEntry)
class PayoutLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["host", "entry_type", "amount", "created_at"]
    list_filter = ["entry_type"]
    search_fields = ["host__email"]
    readonly_fields = [f.name for f in PayoutLedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False
