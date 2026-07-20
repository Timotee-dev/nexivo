"""Tests for analytics service functions."""

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import HostProfile, User
from analytics.services import event_analytics, host_dashboard, platform_dashboard
from bookings.services import create_booking
from events.models import Event, TicketType
from payments.services import initialize_payment, verify_and_finalize_payment
from payments.models import Payment


def full_setup():
    host = User.objects.create_user(email="host@a.test", password="pass", username="host", role=User.Role.HOST)
    p = HostProfile.objects.create(user=host, nin_verified=True, bank_details_verified=True)
    p.refresh_paid_ticket_eligibility()
    cust = User.objects.create_user(email="cust@a.test", password="pass", username="cust", role=User.Role.CUSTOMER)
    event = Event.objects.create(
        host=host, title="Analytics Event", description="d",
        event_type=Event.EventType.VIRTUAL, virtual_platform="Zoom",
        start_datetime=timezone.now() + datetime.timedelta(days=5),
        end_datetime=timezone.now() + datetime.timedelta(days=5, hours=2),
        status=Event.Status.PUBLISHED,
    )
    tt = TicketType.objects.create(event=event, name="General", price=0, quantity_total=50, quantity_remaining=50)
    return host, cust, event, tt


class AnalyticsTest(TestCase):
    def setUp(self):
        self.host, self.cust, self.event, self.tt = full_setup()

    def test_host_dashboard_empty_state(self):
        data = host_dashboard(self.host)
        self.assertEqual(data["total_events"], 1)
        self.assertEqual(data["total_bookings"], 0)
        self.assertEqual(data["total_revenue"], "0")

    def test_host_dashboard_after_purchase(self):
        booking = create_booking(
            customer=self.cust, event_id=self.event.id,
            items=[{"ticket_type_id": self.tt.id, "quantity": 2}]
        )
        with patch("payments.gateways.paystack.PaystackClient.initialize_transaction") as m:
            m.return_value = {"checkout_url": "https://fake.url", "raw": {}}
            initialize_payment(booking=booking, gateway="paystack")
        payment = Payment.objects.first()
        with patch("payments.gateways.paystack.PaystackClient.verify_transaction") as m:
            m.return_value = {"status": "success", "amount": payment.amount, "currency": "NGN", "gateway_transaction_id": "TX"}
            verify_and_finalize_payment(payment)

        data = host_dashboard(self.host)
        self.assertEqual(data["total_bookings"], 1)
        self.assertGreater(Decimal(data["total_revenue"]), 0)

    def test_platform_dashboard_counts_users(self):
        data = platform_dashboard()
        self.assertGreaterEqual(data["total_users"], 2)

    def test_event_analytics_capacity(self):
        data = event_analytics(self.event)
        self.assertEqual(data["total_capacity"], 50)
        self.assertEqual(data["tickets_sold"], 0)
