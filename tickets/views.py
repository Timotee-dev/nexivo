from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from events.models import Event
from tickets.models import Ticket, TicketScanLog, TicketTransfer
from tickets.scanning import process_scan
from tickets.serializers import (
    BulkScanSyncSerializer,
    InitiateTransferSerializer,
    RespondTransferSerializer,
    ScanRequestSerializer,
    ScanResultSerializer,
    TicketScanLogSerializer,
    TicketSerializer,
    TicketTransferSerializer,
)

TRANSFER_EXPIRY_HOURS = 48


class MyTicketsView(generics.ListAPIView):
    """GET /api/v1/tickets/mine/ — all tickets currently held by the authenticated user."""

    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Ticket.objects.filter(holder=self.request.user)
            .select_related("event", "ticket_type")
            .order_by("-created_at")
        )


class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "ticket_code"

    def get_queryset(self):
        if self.request.user.is_super_admin:
            return Ticket.objects.all()
        return Ticket.objects.filter(holder=self.request.user)


def _ensure_host_or_admin(request, event):
    if event.host != request.user and not request.user.is_super_admin:
        raise PermissionDenied("Only the event host or a super admin can scan tickets for this event.")


class ScanTicketView(APIView):
    """
    POST /api/v1/tickets/scan/<event_id>/
    Real-time check-in scan, used when the scanner device is online.
    Restricted to the event's host (or co-scanners they've authorized — see
    note below) and super admin.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = generics.get_object_or_404(Event, pk=event_id)
        _ensure_host_or_admin(request, event)

        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = process_scan(
            event=event,
            code=serializer.validated_data["code"],
            scanned_by=request.user,
            client_scanned_at=serializer.validated_data.get("client_scanned_at"),
            device_id=serializer.validated_data.get("device_id", ""),
            was_offline_sync=False,
        )

        http_status = 200 if result["result"] == TicketScanLog.Result.SUCCESS else 409
        return Response(ScanResultSerializer(result).data, status=http_status)


class BulkScanSyncView(APIView):
    """
    POST /api/v1/tickets/scan/<event_id>/sync/
    Replays a batch of scans that were queued on-device while offline.
    Each scan is validated against the *current* server state in the order
    submitted, using each scan's own client_scanned_at, so duplicate
    detection is correct even if the same ticket was (incorrectly) scanned
    twice offline by different devices — the first to sync wins, the second
    correctly comes back as a duplicate.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = generics.get_object_or_404(Event, pk=event_id)
        _ensure_host_or_admin(request, event)

        serializer = BulkScanSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for scan in serializer.validated_data["scans"]:
            result = process_scan(
                event=event,
                code=scan["code"],
                scanned_by=request.user,
                client_scanned_at=scan.get("client_scanned_at"),
                device_id=scan.get("device_id", ""),
                was_offline_sync=True,
            )
            results.append(ScanResultSerializer(result).data)

        return Response({"synced_count": len(results), "results": results})


class EventScanLogView(generics.ListAPIView):
    """GET /api/v1/tickets/scan/<event_id>/logs/ — host's live check-in feed for an event."""

    serializer_class = TicketScanLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        event = generics.get_object_or_404(Event, pk=self.kwargs["event_id"])
        _ensure_host_or_admin(self.request, event)
        return TicketScanLog.objects.filter(event=event).select_related("scanned_by", "ticket")


class InitiateTransferView(APIView):
    """POST /api/v1/tickets/<ticket_code>/transfer/ — ticket holder sends ticket to another email."""

    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_code):
        ticket = generics.get_object_or_404(Ticket, ticket_code=ticket_code)
        if ticket.holder != request.user:
            raise PermissionDenied("You do not hold this ticket.")
        if not ticket.can_be_transferred:
            return Response({"detail": "This ticket cannot be transferred."}, status=400)

        serializer = InitiateTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["to_email"].lower() == request.user.email.lower():
            raise ValidationError("You cannot transfer a ticket to yourself.")

        transfer = TicketTransfer.objects.create(
            ticket=ticket,
            from_user=request.user,
            to_email=serializer.validated_data["to_email"],
            message=serializer.validated_data.get("message", ""),
            expires_at=timezone.now() + timezone.timedelta(hours=TRANSFER_EXPIRY_HOURS),
            to_user=User.objects.filter(email__iexact=serializer.validated_data["to_email"]).first(),
        )

        from notifications.services import notify_ticket_transfer_initiated
        notify_ticket_transfer_initiated(transfer)

        return Response(TicketTransferSerializer(transfer).data, status=201)


class RespondTransferView(APIView):
    """
    POST /api/v1/tickets/transfers/<transfer_code>/respond/
    Recipient accepts or declines. Accepting requires being logged in with
    an account matching to_email (or to_user if already linked).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, transfer_code):
        transfer = generics.get_object_or_404(TicketTransfer, transfer_code=transfer_code)

        if transfer.to_email.lower() != request.user.email.lower():
            raise PermissionDenied("This transfer was not addressed to your account.")
        if transfer.status != TicketTransfer.Status.PENDING:
            return Response({"detail": f"This transfer has already been {transfer.status}."}, status=400)
        if transfer.is_expired:
            transfer.status = TicketTransfer.Status.EXPIRED
            transfer.save(update_fields=["status"])
            return Response({"detail": "This transfer offer has expired."}, status=400)

        serializer = RespondTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["accept"]:
            ticket = transfer.ticket
            ticket.holder = request.user
            ticket.holder_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            ticket.holder_email = request.user.email
            ticket.save(update_fields=["holder", "holder_name", "holder_email"])

            transfer.status = TicketTransfer.Status.ACCEPTED
            transfer.to_user = request.user
        else:
            transfer.status = TicketTransfer.Status.DECLINED

        transfer.responded_at = timezone.now()
        transfer.save(update_fields=["status", "responded_at", "to_user"])

        if serializer.validated_data["accept"]:
            from notifications.services import notify_ticket_transferred
            notify_ticket_transferred(transfer)

        return Response(TicketTransferSerializer(transfer).data)


class MyTransfersView(generics.ListAPIView):
    """GET /api/v1/tickets/transfers/mine/ — transfers sent or received by the user."""

    serializer_class = TicketTransferSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        return TicketTransfer.objects.filter(
            Q(from_user=self.request.user) | Q(to_email__iexact=self.request.user.email)
        ).select_related("ticket", "ticket__event")


class DownloadTicketPDFView(APIView):
    """GET /api/v1/tickets/<ticket_code>/download/ — serves the ticket PDF."""

    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_code):
        from django.http import FileResponse
        ticket = generics.get_object_or_404(Ticket, ticket_code=ticket_code, holder=request.user)
        if not ticket.pdf_file:
            from tickets.pdf import attach_pdf_to_ticket
            ticket = attach_pdf_to_ticket(ticket)
        return FileResponse(ticket.pdf_file.open("rb"), content_type="application/pdf",
                            as_attachment=True, filename=f"ticket-{ticket.ticket_code}.pdf")
