from django.urls import path
from . import views
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('customer/', views.customer_dash, name='customer_dash'),
    path('provider/', views.provider_dash, name='provider_dash'),
    path('admin/', views.admin_dash, name='admin_dash'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/providers/', views.admin_providers, name='admin_providers'),
    path('admin/bookings/', views.admin_bookings, name='admin_bookings'),
    path('admin/withdrawals/', views.admin_withdrawals, name='admin_withdrawals'),
    path('admin/withdrawals/<int:pk>/approve/', views.approve_wd, name='approve_wd'),
    path('admin/withdrawals/<int:pk>/reject/', views.reject_wd, name='reject_wd'),
    path('admin/providers/<int:pk>/verify/', views.verify_provider, name='verify_provider'),
]
