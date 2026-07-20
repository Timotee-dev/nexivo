import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


from accounts.managers import UserManager
from accounts.encrypted_fields import EncryptedFieldsMixin


class User(AbstractUser):
    """
    Custom user model for Nexivo.

    Supports three roles:
      - super_admin: full platform control
      - host: creates and manages events
      - customer: books tickets

    Email is the primary login identifier. Username is kept (auto-generated)
    for Django admin compatibility but is not used for authentication.
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        HOST = "host", "Event Host"
        CUSTOMER = "customer", "Customer"

    class AccountStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        BANNED = "banned", "Banned"
        PENDING = "pending", "Pending Verification"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(
        max_length=20, blank=True, null=True, unique=True, db_index=True
    )

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE,
        db_index=True,
    )

    # Profile
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)

    # Verification flags
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    # Social auth identifiers
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    apple_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # Security / audit
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["role", "status"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_host(self):
        return self.role == self.Role.HOST

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_account_active(self):
        return self.status == self.AccountStatus.ACTIVE

    def lock_account(self, minutes=15):
        self.locked_until = timezone.now() + timezone.timedelta(minutes=minutes)
        self.save(update_fields=["locked_until"])

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())


class HostProfile(EncryptedFieldsMixin, models.Model):
    ENCRYPTED_FIELDS = ['nin_number', 'account_number']
    """
    Extended profile data for users with role=host.
    Created automatically when a user is promoted to host.
    """

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="host_profile"
    )

    business_name = models.CharField(max_length=255, blank=True, null=True)
    business_description = models.TextField(blank=True, null=True)
    business_logo = models.ImageField(
        upload_to="host_logos/%Y/%m/", blank=True, null=True
    )

    # NIN verification — stored encrypted at rest
    nin_number = models.CharField(max_length=255, blank=True, null=True)
    nin_verified = models.BooleanField(default=False)
    nin_verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    nin_submitted_at = models.DateTimeField(blank=True, null=True)
    nin_verified_at = models.DateTimeField(blank=True, null=True)
    nin_rejection_reason = models.TextField(blank=True, null=True)

    # Bank account for payouts — stored encrypted at rest
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=10, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    account_name = models.CharField(max_length=255, blank=True, null=True)
    paystack_subaccount_code = models.CharField(
        max_length=100, blank=True, null=True, db_index=True
    )
    flutterwave_subaccount_id = models.CharField(
        max_length=100, blank=True, null=True, db_index=True
    )
    stripe_connect_account_id = models.CharField(
        max_length=100, blank=True, null=True, db_index=True
    )
    bank_details_verified = models.BooleanField(default=False)

    # Stats (denormalized for fast dashboard reads; recalculated by signals/tasks)
    total_events_created = models.PositiveIntegerField(default=0)
    total_tickets_sold = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    can_sell_paid_tickets = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "host_profiles"
        indexes = [
            models.Index(fields=["nin_verification_status"]),
        ]

    def __str__(self):
        return f"HostProfile<{self.user.email}>"

    def refresh_paid_ticket_eligibility(self):
        """All hosts can sell paid tickets — no NIN verification required."""
        if not self.can_sell_paid_tickets:
            self.can_sell_paid_tickets = True
            self.save(update_fields=["can_sell_paid_tickets"])
        return True


class CustomerProfile(models.Model):
    """Extended profile data for users with role=customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="customer_profile"
    )

    favorite_events = models.ManyToManyField(
        "events.Event", related_name="favorited_by", blank=True
    )
    followed_hosts = models.ManyToManyField(
        User,
        related_name="followers",
        blank=True,
        limit_choices_to={"role": User.Role.HOST},
    )

    preferred_categories = models.ManyToManyField(
        "events.Category", related_name="interested_customers", blank=True
    )

    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default="Nigeria")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_profiles"

    def __str__(self):
        return f"CustomerProfile<{self.user.email}>"


class AuditLog(models.Model):
    """
    Immutable audit trail for sensitive actions across the platform.
    Written by signals/services, never edited.
    """

    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        LOGIN_FAILED = "login_failed", "Failed Login"
        LOGOUT = "logout", "Logout"
        PASSWORD_CHANGE = "password_change", "Password Change"
        ROLE_CHANGE = "role_change", "Role Change"
        ACCOUNT_SUSPENDED = "account_suspended", "Account Suspended"
        ACCOUNT_BANNED = "account_banned", "Account Banned"
        ACCOUNT_REINSTATED = "account_reinstated", "Account Reinstated"
        EVENT_CREATED = "event_created", "Event Created"
        EVENT_DELETED = "event_deleted", "Event Deleted"
        PAYMENT_PROCESSED = "payment_processed", "Payment Processed"
        REFUND_ISSUED = "refund_issued", "Refund Issued"
        PAYOUT_PROCESSED = "payout_processed", "Payout Processed"
        DISPUTE_RESOLVED = "dispute_resolved", "Dispute Resolved"
        SETTINGS_CHANGED = "settings_changed", "Settings Changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    target_model = models.CharField(max_length=100, blank=True, null=True)
    target_id = models.CharField(max_length=64, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["target_model", "target_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at}"