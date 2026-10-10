from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("verify-email/<str:uidb64>/<str:token>/", views.verify_email, name="verify-email"),
    # Token refresh
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Profile
    path("profile/", views.profile, name="profile"),
    path("change-password/", views.change_password, name="change-password"),
    # Addresses
    path("addresses/", views.AddressListCreateView.as_view(), name="address-list-create"),
    path("addresses/<int:pk>/", views.AddressDetailView.as_view(), name="address-detail"),
]
