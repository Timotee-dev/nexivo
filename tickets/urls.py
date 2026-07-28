from django.urls import path

from tickets.views import (
    BulkScanSyncView,
    EventScanLogView,
    InitiateTransferView,
    MyTicketsView,
    MyTransfersView,
    RespondTransferView,
    ScanTicketView,
    TicketDetailView,
)

app_name = "tickets"

urlpatterns = [
    path("mine/", MyTicketsView.as_view(), name="my_tickets"),
    path("transfers/mine/", MyTransfersView.as_view(), name="my_transfers"),
    path("transfers/<str:transfer_code>/respond/", RespondTransferView.as_view(), name="respond_transfer"),
    path("scan/<uuid:event_id>/", ScanTicketView.as_view(), name="scan"),
    path("scan/<uuid:event_id>/sync/", BulkScanSyncView.as_view(), name="scan_sync"),
    path("scan/<uuid:event_id>/logs/", EventScanLogView.as_view(), name="scan_logs"),
    path("<str:ticket_code>/", TicketDetailView.as_view(), name="ticket_detail"),
    path("<str:ticket_code>/transfer/", InitiateTransferView.as_view(), name="initiate_transfer"),
]
# Added after initial build
from tickets.views import DownloadTicketPDFView, PublicScanView
urlpatterns.append(path("<str:ticket_code>/download/", DownloadTicketPDFView.as_view(), name="download_pdf"))
urlpatterns.append(path("public-scan/<slug:slug>/", PublicScanView.as_view(), name="public_scan"))