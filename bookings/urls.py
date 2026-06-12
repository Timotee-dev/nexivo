from django.urls import path
from . import views
urlpatterns = [
    path('new/<int:pk>/', views.create_booking, name='create_booking'),
    path('<int:pk>/', views.booking_detail, name='booking_detail'),
    path('mine/', views.my_bookings, name='my_bookings'),
    path('manage/', views.manage_bookings, name='manage_bookings'),
    path('<int:pk>/accept/', views.accept_booking, name='accept_booking'),
    path('<int:pk>/reject/', views.reject_booking, name='reject_booking'),
    path('<int:pk>/in-progress/', views.mark_in_progress, name='mark_in_progress'),
    path('<int:pk>/complete/', views.mark_completed, name='mark_completed'),
    path('<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('<int:pk>/review/', views.leave_review, name='leave_review'),
]
