"""
OpenAPI schema extensions for the accounts app.
Import these decorators in views.py via extend_schema to enrich the docs.
"""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

login_schema = extend_schema(
    tags=["auth"],
    summary="Login with email or phone number",
    description="Returns JWT access + refresh tokens. Accepts email address OR phone number as the identifier.",
    responses={200: OpenApiResponse(description="JWT token pair + user profile")},
)

register_schema = extend_schema(
    tags=["auth"],
    summary="Register a new account",
    description="Creates a customer or host account. Role must be 'customer' or 'host'.",
    responses={201: OpenApiResponse(description="JWT token pair + created user")},
)

google_oauth_schema = extend_schema(
    tags=["auth"],
    summary="Sign in with Google",
    description="Accepts a Google ID token (from GSI button) or an authorization code.",
)

apple_oauth_schema = extend_schema(
    tags=["auth"],
    summary="Sign in with Apple",
    description="Accepts an Apple identity JWT token.",
)

webhook_schema = extend_schema(
    tags=["payments"],
    summary="Receive gateway webhook",
    description=(
        "Public endpoint for Paystack, Flutterwave, and Stripe webhook notifications. "
        "Every request's signature is verified cryptographically before processing. "
        "Always returns 200 once signature-verified to prevent gateway redelivery storms."
    ),
    parameters=[OpenApiParameter("gateway", str, OpenApiParameter.PATH, description="paystack | flutterwave | stripe")],
)

checkout_schema = extend_schema(
    tags=["bookings"],
    summary="Initiate ticket checkout",
    description=(
        "Creates a PENDING booking with inventory reserved for 15 minutes, "
        "initialises a gateway payment session, and returns a checkout_url "
        "to redirect the customer to the payment provider's hosted page."
    ),
)

scan_schema = extend_schema(
    tags=["tickets"],
    summary="Scan a ticket QR code (online)",
    description=(
        "Validates a ticket code and marks it as used if valid. "
        "Detects and rejects duplicate scans with full audit logging. "
        "Returns the result synchronously."
    ),
)

offline_sync_schema = extend_schema(
    tags=["tickets"],
    summary="Bulk sync offline scans",
    description=(
        "Replays a batch of scan events that were queued on-device while offline. "
        "Each scan is validated in submission order using its original client_scanned_at timestamp. "
        "Safe to call multiple times (idempotent per code)."
    ),
)
