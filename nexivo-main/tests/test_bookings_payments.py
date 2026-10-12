"""
Tests for the full purchase flow: checkout, inventory locking, payment
verification, ticket generation, QR scanning, duplicate scan prevention.
"""

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import HostProfile, User
from bookings.models import Booking, BookingItem
from bookings.services import cancel_booking, create_booking, expire_stale_bookings
from events.models import Event, TicketType
from payments.models import Payment
from payments.services import initialize_payment, verify_and_finalize_payment
from tickets.models import Ticket, TicketScanLog
from tickets.qr import build_qr_payload, verify_qr_payload
from tickets.scanning import process_scan


def make_setup():
    host = User.objects.create_user(email="host@t.test", password="pass", username="host", role=User.Role.HOST)
    profile = HostProfile.objects.create(user=host, nin_verified=True, bank_details_verified=True)
    profile.refresh_paid_ticket_eligibility()

    cust = User.objects.create_user(email="cust@t.test", password="pass", username="cust", role=User.Role.CUSTOMER)

    event = Event.objects.create(
        host=host, title="Test Event", description="Test",
        event_type=Event.EventType.VIRTUAL, virtual_platform="Zoom",
        start_datetime=timezone.now() + datetime.timedelta(days=5),
        end_datetime=timezone.now() + datetime.timedelta(days=5, hours=2),
        status=Event.Status.PUBLISHED,
    )
    tt = TicketType.objects.create(event=event, name="General", price=0, quantity_total=10, quantity_remaining=10)
    return host, cust, event, tt


class BookingServiceTest(TestCase):
    def setUp(self):
        self.host, self.cust, self.event, self.tt = make_setup()

    def test_create_booking_reserves_inventory(self):
        booking = create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 3}])
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.quantity_remaining, 7)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.ticket_count, 3)

    def test_cannot_overbook(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 20}])

    def test_cancel_booking_releases_inventory(self):
        booking = create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 2}])
        cancel_booking(booking, reason="Test cancel")
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.quantity_remaining, 10)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_expired_bookings_release_inventory(self):
        booking = create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 2}])
        Booking.objects.filter(pk=booking.pk).update(reserved_until=timezone.now() - timezone.timedelta(minutes=1))
        count = expire_stale_bookings()
        self.assertEqual(count, 1)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.quantity_remaining, 10)

    def test_processing_fee_computed_correctly(self):
        from bookings.services import calculate_processing_fee
        from core.models import PlatformSettings
        PlatformSettings.objects.get_or_create(pk=1, defaults={"payment_processing_fee_percent": "1.5", "payment_processing_fee_fixed": "100"})
        fee = calculate_processing_fee(Decimal("10000"))
        self.assertGreater(fee, 0)


class PaymentFlowTest(TestCase):
    def setUp(self):
        self.host, self.cust, self.event, self.tt = make_setup()
        self.booking = create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 2}])

    def test_initialize_payment_creates_record(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            result = initialize_payment(booking=self.booking, gateway="paystack")
        self.assertIn("checkout_url", result)
        self.assertEqual(Payment.objects.count(), 1)

    def test_verify_successful_payment_confirms_booking(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=self.booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": payment.amount, "currency": "NGN", "gateway_transaction_id": "TX1"}
            verify_and_finalize_payment(payment)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_successful_payment_generates_tickets(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=self.booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": payment.amount, "currency": "NGN", "gateway_transaction_id": "TX2"}
            verify_and_finalize_payment(payment)
        tickets = Ticket.objects.filter(booking_item__booking=self.booking)
        self.assertEqual(tickets.count(), 2)

    def test_tickets_have_qr_images(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=self.booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": payment.amount, "currency": "NGN", "gateway_transaction_id": "TX3"}
            verify_and_finalize_payment(payment)
        for ticket in Ticket.objects.all():
            self.assertTrue(ticket.qr_image)

    def test_95_5_split_applied(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=self.booking, gateway="paystack")
        payment = Payment.objects.first()
        self.assertEqual(payment.platform_commission_percent, Decimal("5"))
        expected_commission = (payment.amount * Decimal("5") / 100).quantize(Decimal("0.01"))
        self.assertEqual(payment.platform_commission_amount, expected_commission)

    def test_amount_mismatch_flags_payment(self):
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=self.booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": Decimal("1"), "currency": "NGN", "gateway_transaction_id": "TX4"}
            verify_and_finalize_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.DISPUTED)


class TicketScanTest(TestCase):
    def setUp(self):
        self.host, self.cust, self.event, self.tt = make_setup()
        booking = create_booking(customer=self.cust, event_id=self.event.id, items=[{"ticket_type_id": self.tt.id, "quantity": 1}])
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": payment.amount, "currency": "NGN", "gateway_transaction_id": "TX5"}
            verify_and_finalize_payment(payment)
        self.ticket = Ticket.objects.first()

    def test_qr_payload_encodes_and_decodes(self):
        payload = build_qr_payload(self.ticket.ticket_code)
        decoded = verify_qr_payload(payload)
        self.assertEqual(decoded, self.ticket.ticket_code)

    def test_tampered_payload_fails_verification(self):
        result = verify_qr_payload("FAKE_CODE.BAD_STAMP")
        self.assertIsNone(result)

    def test_valid_scan_succeeds(self):
        payload = build_qr_payload(self.ticket.ticket_code)
        result = process_scan(event=self.event, code=payload, scanned_by=self.host)
        self.assertEqual(result["result"], TicketScanLog.Result.SUCCESS)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.USED)

    def test_duplicate_scan_blocked(self):
        payload = build_qr_payload(self.ticket.ticket_code)
        process_scan(event=self.event, code=payload, scanned_by=self.host)
        result = process_scan(event=self.event, code=payload, scanned_by=self.host)
        self.assertEqual(result["result"], TicketScanLog.Result.DUPLICATE)

    def test_wrong_event_scan_rejected(self):
        other_host = User.objects.create_user(email="h2@t.test", password="pass", username="h2", role=User.Role.HOST)
        HostProfile.objects.create(user=other_host)
        other_event = Event.objects.create(
            host=other_host, title="Other", description="d",
            event_type=Event.EventType.VIRTUAL, virtual_platform="Zoom",
            start_datetime=timezone.now() + datetime.timedelta(days=5),
            end_datetime=timezone.now() + datetime.timedelta(days=5, hours=2),
            status=Event.Status.PUBLISHED,
        )
        payload = build_qr_payload(self.ticket.ticket_code)
        result = process_scan(event=other_event, code=payload, scanned_by=other_host)
        self.assertEqual(result["result"], TicketScanLog.Result.WRONG_EVENT)

    def test_invalid_code_rejected(self):
        result = process_scan(event=self.event, code="INVALID_CODE_XYZ", scanned_by=self.host)
        self.assertEqual(result["result"], TicketScanLog.Result.INVALID)
        log = TicketScanLog.objects.filter(result=TicketScanLog.Result.INVALID).first()
        self.assertIsNotNone(log)
