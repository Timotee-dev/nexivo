from django.urls import path
from . import views
urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_customer, name='register'),
    path('register/provider/', views.register_provider, name='register_provider'),
    path('profile/', views.profile_view, name='profile'),
    path('save/<int:pk>/', views.toggle_save, name='toggle_save'),
    path('notifications/', views.notifications_page, name='notifications'),
    path('notifications/read-all/', views.mark_all_read, name='notif_all_read'),
]
