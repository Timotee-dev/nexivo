from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as Base
from .models import User, ProviderProfile, Notification, SavedProvider
@admin.register(User)
class UserAdmin(Base):
    list_display=['email','get_full_name','role','is_active','date_joined']
    list_filter=['role','is_active']
    search_fields=['email','first_name','last_name']
    fieldsets = Base.fieldsets + (('Role & Contact', {'fields': ('role','phone','city','bio')}),)
@admin.register(ProviderProfile)
class PPAdmin(admin.ModelAdmin):
    list_display=['business_name','user','city','rating','is_verified','available_balance']
admin.site.register(Notification)
admin.site.register(SavedProvider)
