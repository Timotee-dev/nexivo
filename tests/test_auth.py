"""
Tests for accounts: registration, login, JWT, NIN, bank account, OAuth.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import HostProfile, User


def make_user(email="test@nexivo.test", role=User.Role.CUSTOMER, **kwargs):
    return User.objects.create_user(
        email=email, password="TestPass123!", username=email.split("@")[0],
        role=role, first_name="Test", last_name="User", **kwargs
    )


def make_host():
    host = make_user(email="host@nexivo.test", role=User.Role.HOST)
    profile = HostProfile.objects.create(user=host)
    return host, profile


class RegistrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/register/"

    def test_register_customer_success(self):
        resp = self.client.post(self.url, {
            "email": "new@nexivo.test", "password": "StrongPass123!",
            "password_confirm": "StrongPass123!", "first_name": "Ada",
            "last_name": "Okafor", "role": "customer",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["role"], "customer")

    def test_register_host_creates_host_profile(self):
        resp = self.client.post(self.url, {
            "email": "host@nexivo.test", "password": "StrongPass123!",
            "password_confirm": "StrongPass123!", "first_name": "Chidi",
            "last_name": "Eze", "role": "host",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(email="host@nexivo.test")
        self.assertTrue(hasattr(user, "host_profile"))
        self.assertFalse(user.host_profile.can_sell_paid_tickets)

    def test_register_password_mismatch(self):
        resp = self.client.post(self.url, {
            "email": "x@x.com", "password": "Pass123!", "password_confirm": "Diff123!",
            "role": "customer",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_email(self):
        make_user()
        resp = self.client.post(self.url, {
            "email": "test@nexivo.test", "password": "Pass123!", "password_confirm": "Pass123!",
            "role": "customer",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_username_auto_generated_and_unique(self):
        for i in range(3):
            User.objects.create_user(
                email=f"ada{i}@nexivo.test", password="pass",
                username=f"ada{i}", role=User.Role.CUSTOMER
            )
        resp = self.client.post(self.url, {
            "email": "ada0@other.com", "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            "role": "customer",
        }, format="json")
        self.assertEqual(resp.status_code, 201)


class LoginTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.url = "/api/v1/auth/login/"

    def test_login_by_email(self):
        resp = self.client.post(self.url, {"identifier": "test@nexivo.test", "password": "TestPass123!"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)

    def test_login_wrong_password(self):
        resp = self.client.post(self.url, {"identifier": "test@nexivo.test", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_login_increments_failed_attempts(self):
        for _ in range(3):
            self.client.post(self.url, {"identifier": "test@nexivo.test", "password": "wrong"}, format="json")
        self.user.refresh_from_db()
        self.assertGreater(self.user.failed_login_attempts, 0)

    def test_login_by_phone(self):
        user = make_user(email="phone@nexivo.test", phone_number="+2348011111111")
        resp = self.client.post(self.url, {"identifier": "+2348011111111", "password": "TestPass123!"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_me_endpoint_requires_auth(self):
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_correct_user(self):
        login = self.client.post(self.url, {"identifier": "test@nexivo.test", "password": "TestPass123!"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], "test@nexivo.test")

    def test_suspended_user_cannot_login(self):
        self.user.status = User.AccountStatus.SUSPENDED
        self.user.save()
        resp = self.client.post(self.url, {"identifier": "test@nexivo.test", "password": "TestPass123!"}, format="json")
        self.assertEqual(resp.status_code, 400)


class NINVerificationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.host, self.profile = make_host()
        login = self.client.post("/api/v1/auth/login/", {"identifier": "host@nexivo.test", "password": "TestPass123!"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_submit_nin_sets_pending(self):
        resp = self.client.post("/api/v1/auth/host-profile/verify-nin/", {"nin_number": "12345678901"}, format="json")
        self.assertEqual(resp.status_code, 202)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.nin_verification_status, HostProfile.VerificationStatus.PENDING)

    def test_nin_must_be_11_digits(self):
        resp = self.client.post("/api/v1/auth/host-profile/verify-nin/", {"nin_number": "1234"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_customer_cannot_submit_nin(self):
        customer = make_user(email="cust2@nexivo.test")
        login = self.client.post("/api/v1/auth/login/", {"identifier": "cust2@nexivo.test", "password": "TestPass123!"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.post("/api/v1/auth/host-profile/verify-nin/", {"nin_number": "12345678901"}, format="json")
        self.assertEqual(resp.status_code, 403)
