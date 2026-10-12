# affiliates/admin.py
from django.contrib import admin
from affiliates.models import EventAffiliate, AffiliateCommission, AffiliateWithdrawal

@admin.register(EventAffiliate)
class EventAffiliateAdmin(admin.ModelAdmin):
    list_display = ['affiliate_name', 'event', 'commission_rate', 'wallet_balance', 'total_earned', 'is_active']
    search_fields = ['affiliate_name', 'affiliate_email', 'referral_code']
    list_filter = ['is_active', 'event']

@admin.register(AffiliateCommission)
class AffiliateCommissionAdmin(admin.ModelAdmin):
    list_display = ['affiliate', 'commission_amount', 'status', 'created_at']

@admin.register(AffiliateWithdrawal)
class AffiliateWithdrawalAdmin(admin.ModelAdmin):
    list_display = ['affiliate', 'amount', 'status', 'created_at']