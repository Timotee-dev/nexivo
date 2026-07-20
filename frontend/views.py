"""
Server-rendered views for the Nexivo frontend.
Each view is a thin Django view that passes context to a template.
Heavy data fetching happens client-side via the DRF API.
"""

from django.conf import settings
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from events.models import Category, Event


# ── Public pages ──────────────────────────────────────────────────────────

def home(request):
    return render(request, "frontend/home.html", {
        "steps": [
            "Create your event and set ticket tiers",
            "Verify your identity with NIN",
            "Add your bank account for payouts",
            "Publish and start selling instantly",
            "Earn automatically — 95% goes to you",
        ]
    })


def events_list(request):
    categories = Category.objects.filter(is_active=True).order_by("display_order")
    return render(request, "frontend/events_list.html", {"categories": categories})


def event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related("host", "category")
        .prefetch_related("ticket_types", "gallery_images", "reviews__customer"),
        slug=slug,
        status=Event.Status.PUBLISHED,
    )
    Event.objects.filter(pk=event.pk).update(view_count=F("view_count") + 1)
    return render(request, "frontend/event_detail.html", {"event": event})


def event_create(request):
    return render(request, "frontend/event_create.html", {
        "steps": ["Event Details", "Ticket Types", "Banner & Gallery", "Review & Publish"]
    })


# ── Auth pages ────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard_redirect")
    return render(request, "frontend/login.html", {
        "google_client_id": getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
        "captcha_site_key": getattr(settings, "CAPTCHA_SITE_KEY", ""),
    })


def register_view(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard_redirect")
    return render(request, "frontend/register.html")


def checkout_callback(request):
    """Landing page after a gateway redirect. JS verifies payment and redirects."""
    return render(request, "frontend/checkout_callback.html")


# ── Dashboard root ────────────────────────────────────────────────────────

def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    role = getattr(request.user, "role", "customer")
    if role == "super_admin":
        return redirect("/admin-dashboard/")
    if role == "host":
        return redirect("/dashboard/host/")
    return redirect("/dashboard/customer/")


# ── Host dashboard ────────────────────────────────────────────────────────

def host_dashboard(request):
    return render(request, "frontend/dashboard_host.html")


def host_events(request):
    return render(request, "frontend/host_events.html", {
        "statuses": [
            ("",          "All"),
            ("published", "Published"),
            ("draft",     "Draft"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ]
    })


def host_tickets_sold(request):
    return render(request, "frontend/host_tickets_sold.html")


def host_earnings(request):
    return render(request, "frontend/host_earnings.html")


def host_payouts(request):
    return render(request, "frontend/host_payouts.html")


def host_refunds(request):
    return render(request, "frontend/host_refunds.html")


def host_scanner_select(request):
    return render(request, "frontend/host_scanner_select.html")


def host_coupons(request):
    return render(request, "frontend/host_coupons.html")


def host_profile(request):
    return render(request, "frontend/host_profile.html")


def host_verification(request):
    return render(request, "frontend/host_verification.html")


def host_bank_account(request):
    return render(request, "frontend/host_bank_account.html")


# ── Customer dashboard ────────────────────────────────────────────────────

def customer_dashboard(request):
    return render(request, "frontend/dashboard_customer.html")


def customer_tickets(request):
    return render(request, "frontend/customer_tickets.html")


def customer_bookings(request):
    return render(request, "frontend/customer_bookings.html")


def customer_favorites(request):
    return render(request, "frontend/customer_favorites.html")


def customer_following(request):
    return render(request, "frontend/customer_following.html")


def customer_notifications(request):
    return render(request, "frontend/customer_notifications.html")


def customer_profile(request):
    return render(request, "frontend/customer_profile.html")


# ── Admin dashboard ───────────────────────────────────────────────────────

def admin_dashboard(request):
    return render(request, "frontend/dashboard_admin.html")


# ── Scanner ───────────────────────────────────────────────────────────────

def scanner_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    return render(request, "frontend/scanner.html", {"event": event})
