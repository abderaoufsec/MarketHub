from django.urls import path

from . import views

urlpatterns = [
    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("verify-email/<str:uidb64>/<str:token>/", views.verify_email, name="verify-email"),
    # Phase 8 — identity: verification, recovery, phone OTP, social
    path("verify-email/resend/", views.resend_verification, name="resend-verification"),
    path("password/forgot/", views.forgot_password, name="forgot-password"),
    path("password/reset/", views.reset_password, name="reset-password"),
    path("phone/otp/", views.phone_otp_request, name="phone-otp-request"),
    path("phone/login/", views.phone_login, name="phone-login"),
    path("phone/reset/", views.phone_reset_password, name="phone-reset-password"),
    path("phone/verify/", views.phone_verify, name="phone-verify"),
    path("social/", views.social_login, name="social-login"),
    # CSRF cookie for the HttpOnly-cookie session (Phase 7)
    path("csrf/", views.csrf_token, name="csrf-token"),
    # Token refresh (HttpOnly cookie for the web, body for API clients)
    path("token/refresh/", views.CookieTokenRefreshView.as_view(), name="token-refresh"),
    # Profile
    path("profile/", views.profile, name="profile"),
    path("change-password/", views.change_password, name="change-password"),
    # Addresses
    path("addresses/", views.AddressListCreateView.as_view(), name="address-list-create"),
    path("addresses/<int:pk>/", views.AddressDetailView.as_view(), name="address-detail"),
]
