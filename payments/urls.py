from django.urls import path
from . import views

urlpatterns = [
    path('pay/<int:pk>/', views.initiate_payment, name='pay'),
    path('verify/<str:ref>/', views.verify_payment, name='verify_payment'),
    path('receipt/<str:ref>/', views.receipt, name='receipt'),
    path('withdrawals/', views.withdrawals, name='withdrawals'),
    path('bank-setup/', views.bank_setup, name='bank_setup'),
]
