"""affiliates/urls.py"""
from django.urls import path
from affiliates.views import (
    EventAffiliateListCreateView,
    EventAffiliateDetailView,
    AffiliateDashboardView,
    TrackAffiliateClickView,
    ValidateAffiliateCodeView,
    AffiliateBankAccountView,
    AffiliateWithdrawView,
)

app_name = "affiliates"

urlpatterns = [
    # Host manages affiliates for their event
    path("events/<slug:slug>/", EventAffiliateListCreateView.as_view(), name="event_affiliates"),
    path("<uuid:affiliate_id>/", EventAffiliateDetailView.as_view(), name="affiliate_detail"),

    # Affiliate views their own dashboard
    path("my/", AffiliateDashboardView.as_view(), name="my_affiliates"),

    # Public — track clicks and validate codes
    path("track/", TrackAffiliateClickView.as_view(), name="track"),
    path("validate/<str:code>/", ValidateAffiliateCodeView.as_view(), name="validate"),

    # Affiliate bank account and withdrawal
    path("<uuid:affiliate_id>/bank-account/", AffiliateBankAccountView.as_view(), name="bank_account"),
    path("<uuid:affiliate_id>/withdraw/", AffiliateWithdrawView.as_view(), name="withdraw"),
]