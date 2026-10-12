from django.urls import path

from frontend.views import (
    # Core pages
    home,
    help_centre,
    contact_view,
    terms_view,
    privacy_view,
    events_list,
    event_detail,
    event_create,
    login_view,
    register_view,
    checkout_callback,
    # Dashboard routing
    dashboard_redirect,
    # Host dashboard
    host_dashboard,
    host_events,
    host_tickets_sold,
    host_earnings,
    host_payouts,
    host_refunds,
    host_scanner_select,
    host_coupons,
    host_profile,
    host_verification,
    host_bank_account,
    # Customer dashboard
    customer_dashboard,
    customer_tickets,
    customer_bookings,
    customer_favorites,
    customer_following,
    customer_notifications,
    customer_profile,
    # Admin dashboard
    admin_dashboard,
    # Scanner
    scanner_view,
    public_checkin,
    ticket_verify,
    marketer_dashboard,
    host_affiliates,
    affiliate_dashboard,
)

app_name = "frontend"

urlpatterns = [
    # ── Public pages ──────────────────────────────────────────────────────
    path("",                            home,              name="home"),
    path("events/",                     events_list,       name="events_list"),
    path("events/create/",              event_create,      name="event_create"),
    path("events/<slug:slug>/",         event_detail,      name="event_detail"),

    # ── Auth ───────────────────────────────────────────────────────────────
    path("auth/login/",                 login_view,        name="login"),
    path("auth/register/",              register_view,     name="register"),
    path("checkout/callback/",          checkout_callback, name="checkout_callback"),

    # ── Dashboard root (redirects by role) ────────────────────────────────
    path("dashboard/",                  dashboard_redirect, name="dashboard_redirect"),

    # ── Host dashboard sub-pages ──────────────────────────────────────────
    path("dashboard/host/",             host_dashboard,     name="host_dashboard"),
    path("dashboard/events/",           host_events,        name="host_events"),
    path("dashboard/tickets/",          host_tickets_sold,  name="host_tickets_sold"),
    path("dashboard/earnings/",         host_earnings,      name="host_earnings"),
    path("dashboard/payouts/",          host_payouts,       name="host_payouts"),
    path("dashboard/refunds/",          host_refunds,       name="host_refunds"),
    path("dashboard/scanner/",          host_scanner_select, name="host_scanner_select"),
    path("dashboard/coupons/",          host_coupons,       name="host_coupons"),
    path("dashboard/profile/",          host_profile,       name="host_profile"),
    path("dashboard/verification/",     host_verification,  name="host_verification"),
    path("dashboard/bank-account/",     host_bank_account,  name="host_bank_account"),

    # ── Customer dashboard sub-pages ──────────────────────────────────────
    path("dashboard/customer/",         customer_dashboard,     name="customer_dashboard"),
    path("dashboard/my-tickets/",       customer_tickets,       name="customer_tickets"),
    path("dashboard/bookings/",         customer_bookings,      name="customer_bookings"),
    path("dashboard/favorites/",        customer_favorites,     name="customer_favorites"),
    path("dashboard/following/",        customer_following,     name="customer_following"),
    path("dashboard/notifications/",    customer_notifications, name="customer_notifications"),
    path("dashboard/my-profile/",       customer_profile,       name="customer_profile"),

    # ── Admin dashboard ────────────────────────────────────────────────────
    path("admin-dashboard/",            admin_dashboard,    name="admin_dashboard"),

    # ── QR Scanner ────────────────────────────────────────────────────────
    path("dashboard/scanner/<uuid:event_id>/", scanner_view, name="scanner"),
    path("checkin/<slug:slug>/", public_checkin, name="public_checkin"),
    path("help/", help_centre, name="help"),
    path("contact/", contact_view, name="contact"),
    path("terms/", terms_view, name="terms"),
    path("privacy/", privacy_view, name="privacy"),
    path("checkin/verify/<str:payload>/", ticket_verify, name="ticket_verify"),
    path("dashboard/events/<slug:slug>/affiliates/", host_affiliates, name="host_affiliates"),
    path("dashboard/marketer/", marketer_dashboard, name="marketer_dashboard"),
    path("affiliate/<uuid:affiliate_id>/", affiliate_dashboard, name="affiliate_dashboard"),
]