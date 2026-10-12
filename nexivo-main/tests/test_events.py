"""
Tests for events: CRUD, search/filter, publish lifecycle, NIN gate, geolocation.
"""

import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import HostProfile, User
from events.models import Category, Event, TicketType


def make_verified_host():
    host = User.objects.create_user(
        email="host@nexivo.test", password="pass", username="host1", role=User.Role.HOST
    )
    p = HostProfile.objects.create(user=host, nin_verified=True, bank_details_verified=True)
    p.refresh_paid_ticket_eligibility()
    return host


def make_customer():
    return User.objects.create_user(email="cust@nexivo.test", password="pass", username="cust1", role=User.Role.CUSTOMER)


def make_event(host, **kwargs):
    defaults = dict(
        title="Test Event", description="desc",
        event_type=Event.EventType.VIRTUAL, virtual_platform="Zoom",
        start_datetime=timezone.now() + datetime.timedelta(days=5),
        end_datetime=timezone.now() + datetime.timedelta(days=5, hours=2),
        status=Event.Status.PUBLISHED,
    )
    defaults.update(kwargs)
    return Event.objects.create(host=host, **defaults)


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class EventListTest(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Tech")
        self.host = make_verified_host()
        self.event = make_event(self.host, title="Lagos Tech Summit", category=self.cat, city="Lagos")
        TicketType.objects.create(event=self.event, name="General", price=0, quantity_total=100, quantity_remaining=100)

    def test_public_list_returns_published(self):
        resp = self.client.get("/api/v1/events/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_draft_not_in_public_list(self):
        make_event(self.host, title="Draft", status=Event.Status.DRAFT)
        resp = self.client.get("/api/v1/events/")
        self.assertEqual(resp.data["count"], 1)

    def test_search_by_title(self):
        resp = self.client.get("/api/v1/events/?search=Tech")
        self.assertEqual(resp.data["count"], 1)

    def test_search_no_match(self):
        resp = self.client.get("/api/v1/events/?search=Ballet")
        self.assertEqual(resp.data["count"], 0)

    def test_filter_by_city(self):
        resp = self.client.get("/api/v1/events/?city=Lagos")
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_wrong_city(self):
        resp = self.client.get("/api/v1/events/?city=Abuja")
        self.assertEqual(resp.data["count"], 0)

    def test_trending_endpoint(self):
        resp = self.client.get("/api/v1/events/trending/")
        self.assertEqual(resp.status_code, 200)

    def test_upcoming_endpoint(self):
        resp = self.client.get("/api/v1/events/upcoming/")
        self.assertEqual(resp.status_code, 200)


class EventCRUDTest(TestCase):
    def setUp(self):
        self.host = make_verified_host()
        self.client = auth_client(self.host)

    def test_create_virtual_event(self):
        resp = self.client.post("/api/v1/events/mine/", {
            "title": "New Virtual Event", "description": "Test",
            "event_type": "virtual", "virtual_platform": "Zoom",
            "start_datetime": (timezone.now() + datetime.timedelta(days=10)).isoformat(),
            "end_datetime": (timezone.now() + datetime.timedelta(days=10, hours=2)).isoformat(),
            "ticket_types": [{"name": "Free", "price": "0", "quantity_total": 50}],
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "draft")

    def test_publish_event(self):
        event = make_event(self.host, status=Event.Status.DRAFT)
        TicketType.objects.create(event=event, name="Free", price=0, quantity_total=50, quantity_remaining=50)
        resp = self.client.post(f"/api/v1/events/{event.slug}/publish/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "published")

    def test_cannot_publish_without_ticket(self):
        event = make_event(self.host, status=Event.Status.DRAFT)
        resp = self.client.post(f"/api/v1/events/{event.slug}/publish/")
        self.assertEqual(resp.status_code, 400)

    def test_unverified_host_cannot_create_paid_tickets(self):
        unverified = User.objects.create_user(email="unv@nexivo.test", password="pass", username="unv", role=User.Role.HOST)
        HostProfile.objects.create(user=unverified)
        c = auth_client(unverified)
        resp = c.post("/api/v1/events/mine/", {
            "title": "Paid Event", "description": "Test",
            "event_type": "virtual", "virtual_platform": "Zoom",
            "start_datetime": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
            "end_datetime": (timezone.now() + datetime.timedelta(days=5, hours=2)).isoformat(),
            "ticket_types": [{"name": "VIP", "price": "5000", "quantity_total": 50}],
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_unverified_host_can_create_free_event(self):
        unverified = User.objects.create_user(email="unv2@nexivo.test", password="pass", username="unv2", role=User.Role.HOST)
        HostProfile.objects.create(user=unverified)
        c = auth_client(unverified)
        resp = c.post("/api/v1/events/mine/", {
            "title": "Free Event", "description": "Test",
            "event_type": "virtual", "virtual_platform": "Zoom",
            "start_datetime": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
            "end_datetime": (timezone.now() + datetime.timedelta(days=5, hours=2)).isoformat(),
            "ticket_types": [{"name": "Free", "price": "0", "quantity_total": 100}],
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_other_host_cannot_edit_event(self):
        other = User.objects.create_user(email="other@nexivo.test", password="pass", username="other", role=User.Role.HOST)
        HostProfile.objects.create(user=other)
        event = make_event(self.host)
        c = auth_client(other)
        resp = c.patch(f"/api/v1/events/{event.slug}/", {"title": "Hijacked"}, format="json")
        self.assertEqual(resp.status_code, 403)


class NearbyEventsTest(TestCase):
    def setUp(self):
        host = make_verified_host()
        self.event = make_event(
            host, title="Lagos Event", event_type=Event.EventType.PHYSICAL,
            venue_name="Eko Centre", address="VI", city="Lagos",
            latitude="6.4281", longitude="3.4219",
        )
        TicketType.objects.create(event=self.event, name="Free", price=0, quantity_total=50, quantity_remaining=50)

    def test_nearby_returns_events_within_radius(self):
        resp = self.client.get("/api/v1/events/nearby/?lat=6.45&lng=3.40&radius_km=20")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertIn("distance_km", resp.data[0])

    def test_nearby_excludes_distant_events(self):
        resp = self.client.get("/api/v1/events/nearby/?lat=9.0574&lng=7.4898&radius_km=10")  # Abuja
        self.assertEqual(len(resp.data), 0)

    def test_nearby_missing_params(self):
        resp = self.client.get("/api/v1/events/nearby/")
        self.assertEqual(resp.status_code, 400)
