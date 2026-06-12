from django.urls import path
from . import views
urlpatterns = [
    path('', views.home, name='home'),
    path('services/', views.service_list, name='services'),
    path('services/<int:pk>/', views.service_detail, name='service_detail'),
    path('my-services/', views.my_services, name='my_services'),
    path('my-services/new/', views.service_create, name='service_create'),
    path('my-services/<int:pk>/edit/', views.service_edit, name='service_edit'),
    path('my-services/<int:pk>/delete/', views.service_delete, name='service_delete'),
]
