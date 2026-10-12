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
            "Add your bank account for payouts",
            "Publish and start selling instantly",
            "Customers book and pay securely",
            "Earn automatically — 95% goes to you",
        ]
    })


def events_list(request):
    categories = Category.objects.filter(is_active=True).order_by("display_order")
    return render(request, "frontend/events_list.html", {"categories": categories})


def event_detail(request, slug):
    # Allow both PUBLISHED and UPCOMING events to be viewed (upcoming shows info, not ticket purchase)
    event = get_object_or_404(
        Event.objects.select_related("host", "category")
        .prefetch_related("ticket_types", "gallery_images", "reviews__customer"),
        slug=slug,
        status__in=[Event.Status.PUBLISHED, Event.Status.UPCOMING],
    )
    Event.objects.filter(pk=event.pk).update(view_count=F("view_count") + 1)
    return render(request, "frontend/event_detail.html", {"event": event})


def upcoming_events(request):
    """Page showing all UPCOMING events — announced but ticket sales not yet open."""
    from django.utils import timezone
    events = (
        Event.objects.filter(status=Event.Status.UPCOMING, end_datetime__gte=timezone.now())
        .select_related("host", "category")
        .prefetch_related("ticket_types")
        .order_by("start_datetime")
    )
    categories = Category.objects.filter(is_active=True).order_by("display_order")
    return render(request, "frontend/upcoming_events.html", {
        "events": events,
        "categories": categories,
    })


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

# Add this function to frontend/views.py

def public_checkin(request, slug):
    from events.models import Event
    try:
        event = Event.objects.get(slug=slug, status='published')
    except Event.DoesNotExist:
        from django.http import Http404
        raise Http404
    return render(request, 'frontend/checkin.html', {'event': event})

def ticket_verify(request, payload):
    """
    Public ticket verification page — opened when anyone scans a Nexivo QR code.
    Shows a beautiful welcome/invalid screen without requiring login.
    """
    from tickets.qr import verify_qr_payload

    ticket_code = verify_qr_payload(payload)
    event_slug = ''

    if ticket_code:
        try:
            from tickets.models import Ticket
            ticket = Ticket.objects.select_related('ticket_type__event').get(ticket_code=ticket_code)
            event_slug = ticket.ticket_type.event.slug
        except Exception:
            pass

    return render(request, 'frontend/ticket_verify.html', {
        'payload': payload,
        'event_slug': event_slug,
    })

def help_centre(request):
    faqs = [
        {"title": "For Attendees", "questions": [
            {"q": "How do I buy a ticket?", "a": "Browse events, select your ticket type, and pay securely with Paystack. You receive a QR code ticket instantly."},
            {"q": "How do I access my tickets?", "a": "Log in and go to Dashboard then My Tickets. Your QR code will be there."},
            {"q": "Can I get a refund?", "a": "Refund policies are set by each event organizer. Check the event page before purchasing."},
            {"q": "Can I transfer my ticket?", "a": "Yes. Go to My Tickets and click Transfer on the ticket you want to send."},
        ]},
        {"title": "For Organisers", "questions": [
            {"q": "How do I create an event?", "a": "Register as a host, go to Dashboard, click Create Event, fill in details and ticket types, then publish."},
            {"q": "When do I get paid?", "a": "95% of ticket sales go directly to your bank account via Paystack on the next business day."},
            {"q": "Is there a fee?", "a": "Nexivo takes 5% per ticket sold. You keep 95% of all revenue."},
        ]},
    ]
    return render(request, "frontend/help.html", {"faqs": faqs})

def contact_view(request):
    return render(request, "frontend/contact.html")

def terms_view(request):
    sections = [
        {"title": "Acceptance of Terms", "content": "By using Nexivo, you agree to these Terms of Service."},
        {"title": "Ticket Purchases", "content": "All ticket purchases are final unless the organizer offers refunds. A 5% platform fee is deducted from all sales."},
        {"title": "Organizer Responsibilities", "content": "Organizers must deliver their advertised events and honor their refund policies."},
        {"title": "Limitation of Liability", "content": "Nexivo is not liable for damages arising from events booked through the platform."},
    ]
    return render(request, "frontend/terms.html", {"sections": sections})

def privacy_view(request):
    sections = [
        {"title": "Information We Collect", "content": "We collect your name, email, and phone number when you register, and booking history when you use the platform."},
        {"title": "How We Use It", "content": "We use your information to process bookings, send QR code tickets, and communicate booking updates."},
        {"title": "Payment Information", "content": "All payments are processed by Paystack. Nexivo does not store card details."},
        {"title": "Your Rights", "content": "You can delete your account anytime from your dashboard. For data deletion email teetimo29@gmail.com"},
    ]
    return render(request, "frontend/privacy.html", {"sections": sections})


def marketer_dashboard(request):
    return render(request, "frontend/marketer_dashboard.html")

def host_affiliates(request, slug):
    """Host manages affiliates for a specific event."""
    if not request.user.is_authenticated:
        return redirect('/auth/login/')
    from events.models import Event
    from django.http import Http404
    try:
        event = Event.objects.get(slug=slug, host=request.user)
    except Event.DoesNotExist:
        raise Http404
    return render(request, 'frontend/host_affiliates.html', {'event': event})

def host_affiliates(request, slug):
    return render(request, 'frontend/host_affiliates.html', {'event_slug': slug})

def affiliate_dashboard(request, affiliate_id):
    """Public affiliate dashboard — no login needed."""
    return render(request, 'frontend/affiliate_dashboard.html', {
        'affiliate_id': affiliate_id,
    })