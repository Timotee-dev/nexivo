from django.urls import path

from payouts.views import (
    AdminAllPayoutsView,
    AdminHoldPayoutView,
    AdminReleasePayoutView,
    AdminTriggerPayoutsView,
    MyBalanceView,
    MyLedgerView,
    MyPayoutsView,
)

app_name = "payouts"

urlpatterns = [
    path("mine/", MyPayoutsView.as_view(), name="my_payouts"),
    path("balance/", MyBalanceView.as_view(), name="my_balance"),
    path("ledger/", MyLedgerView.as_view(), name="my_ledger"),
    path("admin/all/", AdminAllPayoutsView.as_view(), name="admin_all"),
    path("admin/run/", AdminTriggerPayoutsView.as_view(), name="admin_run"),
    path("admin/<uuid:payout_id>/hold/", AdminHoldPayoutView.as_view(), name="admin_hold"),
    path("admin/<uuid:payout_id>/release/", AdminReleasePayoutView.as_view(), name="admin_release"),
]
