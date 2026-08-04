"""marketers/urls.py"""
from django.urls import path
from marketers.views import (
    MarketerRegisterView,
    MarketerDashboardView,
    MarketerBankAccountView,
    MarketerWithdrawView,
    ValidateReferralCodeView,
)

app_name = "marketers"

urlpatterns = [
    path("register/",              MarketerRegisterView.as_view(),    name="register"),
    path("dashboard/",             MarketerDashboardView.as_view(),   name="dashboard"),
    path("bank-account/",          MarketerBankAccountView.as_view(), name="bank_account"),
    path("withdraw/",              MarketerWithdrawView.as_view(),    name="withdraw"),
    path("validate/<str:code>/",   ValidateReferralCodeView.as_view(), name="validate"),
]