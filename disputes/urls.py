from django.urls import path
from disputes.views import (
    AdminAllDisputesView, AdminResolveDisputeView,
    AddDisputeMessageView, DisputeDetailView, MyDisputesView,
)

app_name = "disputes"

urlpatterns = [
    path("mine/", MyDisputesView.as_view(), name="my_disputes"),
    path("admin/all/", AdminAllDisputesView.as_view(), name="admin_all"),
    path("<uuid:pk>/", DisputeDetailView.as_view(), name="detail"),
    path("<uuid:pk>/resolve/", AdminResolveDisputeView.as_view(), name="resolve"),
    path("<uuid:pk>/message/", AddDisputeMessageView.as_view(), name="add_message"),
]
