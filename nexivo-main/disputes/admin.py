from django.contrib import admin
from disputes.models import Dispute, DisputeMessage

class DisputeMessageInline(admin.TabularInline):
    model = DisputeMessage
    extra = 0
    readonly_fields = ["author", "created_at"]

@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ["reference", "raised_by", "against_host", "category", "status", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["reference", "raised_by__email", "subject"]
    inlines = [DisputeMessageInline]
    readonly_fields = ["id", "reference", "created_at", "updated_at"]
