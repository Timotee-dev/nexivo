from django.contrib import admin

from tickets.models import Ticket, TicketScanLog, TicketTransfer


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["ticket_code", "event", "holder", "ticket_type", "status", "checked_in_at"]
    list_filter = ["status", "event"]
    search_fields = ["ticket_code", "barcode_value", "holder_email", "holder_name"]
    readonly_fields = ["id", "ticket_code", "barcode_value", "qr_image", "created_at", "updated_at"]


@admin.register(TicketScanLog)
class TicketScanLogAdmin(admin.ModelAdmin):
    list_display = ["event", "scanned_code", "result", "scanned_by", "was_offline_sync", "created_at"]
    list_filter = ["result", "was_offline_sync"]
    readonly_fields = [f.name for f in TicketScanLog._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(TicketTransfer)
class TicketTransferAdmin(admin.ModelAdmin):
    list_display = ["ticket", "from_user", "to_email", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["ticket__ticket_code", "from_user__email", "to_email"]
