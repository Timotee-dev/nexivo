"""
Social OAuth handling for Google and Apple sign-in.
Both flows work the same way from the server's perspective:
  1. Frontend redirects user to provider (Google/Apple hosted consent page)
  2. Provider redirects back with a code
  3. Our callback view exchanges the code for tokens and gets a profile
  4. We find-or-create a local User, issue our JWT, return it to the frontend

Google: uses google-auth library for ID token verification (preferred over
code exchange since the frontend typically receives an ID token via Google
Sign-In button). Accepts both code flow and ID-token-verify flow.

Apple: uses the Sign in with Apple code flow. Apple issues an identity JWT
which we verify using Apple's public keys.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger("nexivo")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


def verify_google_id_token(id_token: str) -> dict | None:
    """
    Verifies a Google ID token issued by the Sign-In button JS library.
    Returns the decoded payload (sub, email, name, picture) or None.
    """
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        payload = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
        return payload
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        return None


def exchange_google_code(code: str, redirect_uri: str) -> dict | None:
    """Exchanges an authorization code for tokens and returns userinfo."""
    try:
        token_resp = requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=10)
        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            return None
        userinfo = requests.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        return userinfo.json()
    except Exception as exc:
        logger.warning("Google code exchange failed: %s", exc)
        return None


def verify_apple_token(identity_token: str) -> dict | None:
    """
    Verifies an Apple identity JWT and returns its decoded payload.
    Uses Apple's published JWKS for signature verification.
    """
    try:
        import jwt
        from jwt import PyJWKClient
        jwks_client = PyJWKClient(APPLE_KEYS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(identity_token)
        payload = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.APPLE_OAUTH_CLIENT_ID,
        )
        return payload
    except Exception as exc:
        logger.warning("Apple identity token verification failed: %s", exc)
        return None


def find_or_create_social_user(*, provider: str, provider_id: str, email: str,
                                first_name: str = "", last_name: str = "",
                                avatar_url: str = "", role: str = "customer"):
    """
    Finds an existing user by provider ID or email, creates one if not found.
    Returns (user, created_bool).
    """
    from accounts.models import CustomerProfile, HostProfile, User

    lookup_field = f"{provider}_id"
    existing = User.objects.filter(**{lookup_field: provider_id}).first()
    if existing:
        return existing, False

    # Try match by email (user may have registered by email previously)
    if email:
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            setattr(existing, lookup_field, provider_id)
            existing.email_verified = True
            existing.save(update_fields=[lookup_field, "email_verified"])
            return existing, False

    # Create new user
    base_username = email.split("@")[0] if email else provider_id
    username = base_username
    suffix = 0
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base_username}{suffix}"

    user = User.objects.create_user(
        email=email or f"{provider_id}@{provider}.social",
        username=username,
        first_name=first_name,
        last_name=last_name,
        role=role,
        email_verified=True,
        **{lookup_field: provider_id},
    )
    user.set_unusable_password()
    user.save()

    if role == User.Role.HOST:
        HostProfile.objects.create(user=user)
    else:
        CustomerProfile.objects.create(user=user)

    # Download avatar asynchronously (best effort)
    if avatar_url:
        try:
            _attach_avatar(user, avatar_url)
        except Exception:
            pass

    return user, True


def _attach_avatar(user, url: str):
    import io
    from django.core.files.base import ContentFile
    resp = requests.get(url, timeout=8)
    if resp.status_code == 200:
        ext = "jpg"
        user.avatar.save(f"avatar_{user.id}.{ext}", ContentFile(resp.content), save=True)
