from django.urls import path

from payments.views import (
    AdminAllPaymentsView,
    AdminFlaggedPaymentsView,
    AdminReconciliationView,
    AdminWebhookEventsView,
    HostRefundsView,
    MyPaymentsView,
    MyRefundsView,
    PaymentDetailView,
    RefundDecisionView,
    RequestRefundView,
    TriggerReconciliationView,
    VerifyPaymentView,
    WebhookView,
)

app_name = "payments"

urlpatterns = [
    path("mine/", MyPaymentsView.as_view(), name="my_payments"),
    path("verify/", VerifyPaymentView.as_view(), name="verify"),
    path("webhook/<str:gateway>/", WebhookView.as_view(), name="webhook"),

    path("refunds/mine/", MyRefundsView.as_view(), name="my_refunds"),
    path("refunds/pending/", HostRefundsView.as_view(), name="pending_refunds"),
    path("refunds/<uuid:refund_id>/decide/", RefundDecisionView.as_view(), name="refund_decide"),

    path("admin/all/", AdminAllPaymentsView.as_view(), name="admin_all"),
    path("admin/flagged/", AdminFlaggedPaymentsView.as_view(), name="admin_flagged"),
    path("admin/webhook-events/", AdminWebhookEventsView.as_view(), name="admin_webhook_events"),
    path("admin/reconciliation/", AdminReconciliationView.as_view(), name="admin_reconciliation"),
    path("admin/reconcile/", TriggerReconciliationView.as_view(), name="admin_trigger_reconcile"),

    path("<str:gateway_reference>/refund/", RequestRefundView.as_view(), name="request_refund"),
    path("<str:gateway_reference>/", PaymentDetailView.as_view(), name="payment_detail"),
]
