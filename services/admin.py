from django.contrib import admin
from .models import Category, Service
@admin.register(Category)
class CatAdmin(admin.ModelAdmin):
    list_display=['name','emoji','is_active']
    prepopulated_fields={'slug':('name',)}
@admin.register(Service)
class SvcAdmin(admin.ModelAdmin):
    list_display=['title','provider','price','is_active','created_at']
    list_filter=['is_active','category']
