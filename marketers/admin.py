# marketers/admin.py
from django.contrib import admin
from marketers.models import Marketer, MarketerCommission, MarketerWithdrawal

@admin.register(Marketer)
class MarketerAdmin(admin.ModelAdmin):
    list_display = ['user', 'referral_code', 'wallet_balance', 'total_earned', 'is_active']
    search_fields = ['user__email', 'referral_code']

@admin.register(MarketerCommission)
class MarketerCommissionAdmin(admin.ModelAdmin):
    list_display = ['marketer', 'commission_amount', 'status', 'created_at']

@admin.register(MarketerWithdrawal)
class MarketerWithdrawalAdmin(admin.ModelAdmin):
    list_display = ['marketer', 'amount', 'status', 'created_at']