from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve
import os
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # ── Admin ──────────────────────────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ── API v1 ─────────────────────────────────────────────────────────────
    path("api/v1/auth/",          include("accounts.urls")),
    path("api/v1/events/",        include("events.urls")),
    path("api/v1/bookings/",      include("bookings.urls")),
    path("api/v1/tickets/",       include("tickets.urls")),
    path("api/v1/payments/",      include("payments.urls")),
    path("api/v1/payouts/",       include("payouts.urls")),
    path("api/v1/coupons/",       include("coupons.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/reviews/",       include("reviews.urls")),
    path("api/v1/disputes/",      include("disputes.urls")),
    path("api/v1/analytics/",     include("analytics.urls")),
    path("api/v1/marketers/",     include("marketers.urls")),
    path("api/v1/affiliates/",    include("affiliates.urls")),

    # ── API docs ───────────────────────────────────────────────────────────
    path("api/v1/schema/", SpectacularAPIView.as_view(),         name="schema"),
    path("api/docs/",      SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/",     SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),

    # ── ads.txt (Google AdSense) ───────────────────────────────────────────
    path("ads.txt", serve, {"document_root": os.path.join(settings.BASE_DIR, "static"), "path": "ads.txt"}),

    # ── Frontend (server-rendered pages) ──────────────────────────────────
    path("", include("frontend.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)