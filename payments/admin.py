from django.contrib import admin
from .models import Payment, Withdrawal
@admin.register(Payment)
class PA(admin.ModelAdmin):
    list_display=['reference','amount','commission','provider_payout','status','paid_at']
@admin.register(Withdrawal)
class WA(admin.ModelAdmin):
    list_display=['provider','amount','status','bank_name','created_at']
