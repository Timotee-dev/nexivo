from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import (
    AppleOAuthView,
    CaptchaVerifyView,
    ChangePasswordView,
    GoogleOAuthView,
    HostProfileView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    SubmitBankAccountView,
    SubmitNINView,
)

app_name = "accounts"

urlpatterns = [
    # Auth
    path("register/",            RegisterView.as_view(),      name="register"),
    path("login/",               LoginView.as_view(),         name="login"),
    path("logout/",              LogoutView.as_view(),        name="logout"),
    path("token/refresh/",       TokenRefreshView.as_view(),  name="token_refresh"),
    # Profile
    path("me/",                  MeView.as_view(),            name="me"),
    path("change-password/",     ChangePasswordView.as_view(), name="change_password"),
    # Host
    path("host-profile/",        HostProfileView.as_view(),   name="host_profile"),
    path("host-profile/verify-nin/",   SubmitNINView.as_view(),       name="verify_nin"),
    path("host-profile/bank-account/", SubmitBankAccountView.as_view(), name="bank_account"),
    # Security
    path("captcha-verify/",      CaptchaVerifyView.as_view(), name="captcha_verify"),
    # OAuth
    path("oauth/google/",        GoogleOAuthView.as_view(),   name="oauth_google"),
    path("oauth/apple/",         AppleOAuthView.as_view(),    name="oauth_apple"),
]
