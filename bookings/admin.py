from django.contrib import admin
from .models import Booking, Review
@admin.register(Booking)
class BA(admin.ModelAdmin):
    list_display=['ref','service','customer','date','amount','status']
    list_filter=['status']
@admin.register(Review)
class RA(admin.ModelAdmin):
    list_display=['customer','provider','rating','created_at']
