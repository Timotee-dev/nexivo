"""
Role-based DRF permission classes shared across all apps.
Every view in the platform composes permissions from this module rather
than re-implementing role checks inline.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSuperAdmin(BasePermission):
    message = "Only super administrators may perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_super_admin
        )


class IsHost(BasePermission):
    message = "Only event hosts may perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_host
        )


class IsCustomer(BasePermission):
    message = "Only customers may perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_customer
        )


class IsHostOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_host or request.user.is_super_admin)
        )


class IsVerifiedHost(BasePermission):
    """Host must have NIN-verified + bank-verified status to sell paid tickets."""

    message = "You must complete NIN and bank verification before selling paid tickets."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_host):
            return False
        profile = getattr(user, "host_profile", None)
        return bool(profile and profile.can_sell_paid_tickets)


class IsOwnerOrSuperAdmin(BasePermission):
    """
    Object-level permission: only the object's owner (host/customer) or a
    super admin may modify it. Assumes the model has an `owner`-like field;
    override `get_owner` per-view via queryset annotation if the field name differs.
    """

    owner_field = "host"

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_super_admin:
            return True
        owner = getattr(obj, getattr(view, "owner_field", self.owner_field), None)
        return owner == request.user


class ReadOnlyOrSuperAdmin(BasePermission):
    """Anyone may read; only super admin may write. Used for platform-wide reference data."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_super_admin
        )


class IsAccountActive(BasePermission):
    """Blocks suspended/banned users from any write action platform-wide."""

    message = "Your account is suspended or banned. Contact support for assistance."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_account_active
        )
