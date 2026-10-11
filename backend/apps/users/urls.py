from django.urls import path

from . import views

urlpatterns = [
    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("verify-email/<str:uidb64>/<str:token>/", views.verify_email, name="verify-email"),
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
