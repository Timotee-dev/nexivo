"""
Authentication views for Nexivo.
Handles registration, login (email or phone), JWT, OAuth (Google/Apple),
NIN verification submission, and bank account submission.
"""

from django.conf import settings
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import AuditLog, HostProfile, User
from accounts.serializers import (
    BankAccountSerializer,
    ChangePasswordSerializer,
    EmailOrPhoneLoginSerializer,
    HostProfileSerializer,
    NINSubmissionSerializer,
    RegisterSerializer,
    UserSerializer,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["email"] = user.email
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ── Auth ───────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/"""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = _tokens_for_user(user)
        return Response(
            {"user": UserSerializer(user).data, **tokens},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/v1/auth/login/ — email or phone number + password."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOrPhoneLoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        user.last_login_ip = _client_ip(request)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login_ip", "last_login"])

        AuditLog.objects.create(
            actor=user,
            action=AuditLog.Action.LOGIN,
            target_model="User",
            target_id=str(user.id),
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        )

        return Response({"user": UserSerializer(user).data, **_tokens_for_user(user)})


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — blacklists the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required."}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid or already-blacklisted token."}, status=400)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditLog.Action.LOGOUT,
            target_model="User",
            target_id=str(request.user.id),
        )
        return Response({"detail": "Logged out successfully."}, status=205)


class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/v1/auth/me/"""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        AuditLog.objects.create(
            actor=user, action=AuditLog.Action.PASSWORD_CHANGE,
            target_model="User", target_id=str(user.id),
        )
        return Response({"detail": "Password updated."})


# ── Host profile ──────────────────────────────────────────────────────────

class HostProfileView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/v1/auth/host-profile/"""

    serializer_class = HostProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = HostProfile.objects.get_or_create(user=self.request.user)
        return profile


class SubmitNINView(APIView):
    """POST /api/v1/auth/host-profile/verify-nin/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_host:
            return Response({"detail": "Only hosts can submit NIN verification."}, status=403)

        serializer = NINSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile, _ = HostProfile.objects.get_or_create(user=request.user)
        profile.nin_number = serializer.validated_data["nin_number"]
        profile.nin_verification_status = HostProfile.VerificationStatus.PENDING
        profile.nin_submitted_at = timezone.now()
        profile.save(update_fields=["nin_number", "nin_verification_status", "nin_submitted_at"])

        return Response(
            {"detail": "NIN submitted.", "status": profile.nin_verification_status},
            status=202,
        )


class SubmitBankAccountView(APIView):
    """POST /api/v1/auth/host-profile/bank-account/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_host:
            return Response({"detail": "Only hosts can add bank details."}, status=403)

        serializer = BankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile, _ = HostProfile.objects.get_or_create(user=request.user)
        for field, value in serializer.validated_data.items():
            setattr(profile, field, value)
        profile.bank_details_verified = False
        profile.save()

        from payments.tasks import create_host_subaccounts
        create_host_subaccounts(profile.id)

        return Response({"detail": "Bank details submitted. Verification in progress."}, status=202)


# ── CAPTCHA ────────────────────────────────────────────────────────────────

class CaptchaVerifyView(APIView):
    """POST /api/v1/auth/captcha-verify/"""

    permission_classes = [AllowAny]

    def post(self, request):
        from core.security import verify_captcha
        token = request.data.get("captcha_token", "")
        ip = _client_ip(request)
        if not verify_captcha(token, ip):
            return Response({"detail": "CAPTCHA verification failed."}, status=400)

        import secrets
        from django.core.cache import cache
        verified_token = secrets.token_hex(16)
        cache.set(f"captcha_ok:{verified_token}", True, timeout=300)
        return Response({"verified": True, "token": verified_token})


# ── Google OAuth ───────────────────────────────────────────────────────────

class GoogleOAuthView(APIView):
    """
    POST /api/v1/auth/oauth/google/
    Accepts {"id_token": "..."} from the Google Sign-In button, or
    {"code": "...", "redirect_uri": "..."} from the code flow.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        from accounts.oauth import (
            exchange_google_code,
            find_or_create_social_user,
            verify_google_id_token,
        )

        id_token = request.data.get("id_token")
        code = request.data.get("code")
        role = request.data.get("role", "customer")

        if id_token:
            payload = verify_google_id_token(id_token)
        elif code:
            redirect_uri = request.data.get(
                "redirect_uri",
                f"{settings.FRONTEND_URL}/auth/callback/google/",
            )
            payload = exchange_google_code(code, redirect_uri)
        else:
            return Response({"detail": "Provide id_token or code."}, status=400)

        if not payload:
            return Response({"detail": "Google authentication failed."}, status=401)

        user, created = find_or_create_social_user(
            provider="google",
            provider_id=str(payload.get("sub") or payload.get("id", "")),
            email=payload.get("email", ""),
            first_name=payload.get("given_name", ""),
            last_name=payload.get("family_name", ""),
            avatar_url=payload.get("picture", ""),
            role=role,
        )

        if not user.is_account_active:
            return Response({"detail": f"Account is {user.status}."}, status=403)

        return Response(
            {"user": UserSerializer(user).data, **_tokens_for_user(user), "created": created},
            status=201 if created else 200,
        )


# ── Apple OAuth ────────────────────────────────────────────────────────────

class AppleOAuthView(APIView):
    """POST /api/v1/auth/oauth/apple/"""

    permission_classes = [AllowAny]

    def post(self, request):
        from accounts.oauth import find_or_create_social_user, verify_apple_token

        identity_token = request.data.get("identity_token")
        user_data = request.data.get("user", {})
        role = request.data.get("role", "customer")

        if not identity_token:
            return Response({"detail": "identity_token is required."}, status=400)

        payload = verify_apple_token(identity_token)
        if not payload:
            return Response({"detail": "Apple authentication failed."}, status=401)

        name_data = user_data.get("name", {})
        user, created = find_or_create_social_user(
            provider="apple",
            provider_id=payload["sub"],
            email=payload.get("email", ""),
            first_name=name_data.get("firstName", ""),
            last_name=name_data.get("lastName", ""),
            role=role,
        )

        if not user.is_account_active:
            return Response({"detail": f"Account is {user.status}."}, status=403)

        return Response(
            {"user": UserSerializer(user).data, **_tokens_for_user(user), "created": created},
            status=201 if created else 200,
        )