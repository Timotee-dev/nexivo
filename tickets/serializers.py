from rest_framework import serializers

from tickets.models import Ticket, TicketScanLog, TicketTransfer


class TicketSerializer(serializers.ModelSerializer):
    event_title = serializers.CharField(source="event.title", read_only=True)
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)
    is_checked_in = serializers.BooleanField(read_only=True)
    can_be_transferred = serializers.BooleanField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "event", "event_title", "ticket_type", "ticket_type_name",
            "holder_name", "holder_email", "ticket_code", "barcode_value",
            "qr_image", "pdf_file", "status", "seat_label", "checked_in_at",
            "is_checked_in", "can_be_transferred", "created_at",
        ]
        read_only_fields = fields


class ScanRequestSerializer(serializers.Serializer):
    """
    A single scan attempt. `code` is the raw QR payload (ticket_code.stamp)
    or the barcode_value for barcode scanners.
    `client_scanned_at` + `device_id` support offline sync: the scanner app
    queues scans locally while offline and replays them here once reconnected,
    each tagged with the real on-device scan time.
    """

    code = serializers.CharField()
    client_scanned_at = serializers.DateTimeField(required=False)
    device_id = serializers.CharField(required=False, allow_blank=True)


class BulkScanSyncSerializer(serializers.Serializer):
    """POST body for replaying a batch of offline-queued scans at once."""

    scans = ScanRequestSerializer(many=True)


class ScanResultSerializer(serializers.Serializer):
    result = serializers.CharField()
    message = serializers.CharField()
    ticket = TicketSerializer(required=False, allow_null=True)
    checked_in_at = serializers.DateTimeField(required=False, allow_null=True)
    previously_scanned_by = serializers.CharField(required=False, allow_null=True)


class TicketScanLogSerializer(serializers.ModelSerializer):
    scanned_by_name = serializers.CharField(source="scanned_by.username", read_only=True, default=None)

    class Meta:
        model = TicketScanLog
        fields = [
            "id", "ticket", "scanned_code", "result", "scanned_by", "scanned_by_name",
            "client_scanned_at", "was_offline_sync", "device_id", "created_at",
        ]
        read_only_fields = fields


class InitiateTransferSerializer(serializers.Serializer):
    to_email = serializers.EmailField()
    message = serializers.CharField(required=False, allow_blank=True, max_length=255)


class RespondTransferSerializer(serializers.Serializer):
    accept = serializers.BooleanField()


class TicketTransferSerializer(serializers.ModelSerializer):
    ticket_code = serializers.CharField(source="ticket.ticket_code", read_only=True)
    event_title = serializers.CharField(source="ticket.event.title", read_only=True)
    from_user_email = serializers.EmailField(source="from_user.email", read_only=True)

    class Meta:
        model = TicketTransfer
        fields = [
            "id", "ticket", "ticket_code", "event_title", "from_user_email",
            "to_email", "status", "transfer_code", "message",
            "expires_at", "responded_at", "created_at",
        ]
        read_only_fields = fields
