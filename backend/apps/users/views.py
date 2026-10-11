from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .audit import record_auth_event
from .authentication import CookieJWTAuthentication
from .cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from .models import Address, AuthEvent, User
from .security import check_login_backoff, clear_login_failures, record_login_failure
from .serializers import (
    AddressSerializer,
    PasswordChangeSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)
from .throttles import (
    ChangePasswordRateThrottle,
    LoginRateThrottle,
    RegisterRateThrottle,
    TokenRefreshRateThrottle,
    VerifyEmailRateThrottle,
)


def blacklist_all_tokens(user) -> None:
    """Revoke every outstanding refresh token of ``user`` (password change,
    compromised account). Newly issued tokens must be created *after* this."""
    outstanding = list(OutstandingToken.objects.filter(user=user))
    if outstanding:
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=token) for token in outstanding],
            ignore_conflicts=True,
        )


@api_view(["POST"])
@throttle_classes([RegisterRateThrottle])
@permission_classes([AllowAny])
def register(request):
    """User registration endpoint"""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()

        # Send verification email
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        verification_link = f"{settings.FRONTEND_URL}/verify-email/{uid}/{token}/"

        send_mail(
            subject="Verify your MarketHub account",
            message=f"Please click the link to verify your email: {verification_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        record_auth_event(request, AuthEvent.REGISTERED, user=user, is_seller=user.is_seller)

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@throttle_classes([VerifyEmailRateThrottle])
@permission_classes([AllowAny])
def verify_email(request, uidb64, token):
    """Email verification endpoint"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"error": "Invalid verification link"}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        user.is_verified = True
        user.save()
        record_auth_event(request, AuthEvent.EMAIL_VERIFIED, user=user)
        return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)

    return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@throttle_classes([LoginRateThrottle])
@permission_classes([AllowAny])
def login(request):
    """Login endpoint.

    The JWT pair is set as **HttpOnly cookies** and never appears in the
    response body (an XSS hook cannot read it out of a response it did not
    intercept live). Failed attempts feed the per-(IP, email) backoff in
    ``security.py``.
    """
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {"error": "Please provide both email and password"}, status=status.HTTP_400_BAD_REQUEST
        )

    check_login_backoff(request, email)

    user = authenticate(username=email, password=password)

    if user is None:
        record_login_failure(request, email)
        record_auth_event(
            request, AuthEvent.LOGIN_FAILED, email=email, reason="invalid_credentials"
        )
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_verified:
        record_auth_event(request, AuthEvent.LOGIN_FAILED, user=user, reason="email_not_verified")
        return Response(
            {"error": "Please verify your email before logging in"},
            status=status.HTTP_403_FORBIDDEN,
        )

    clear_login_failures(request, email)
    refresh = RefreshToken.for_user(user)
    record_auth_event(request, AuthEvent.LOGIN_SUCCESS, user=user)
    # Prime the CSRF cookie so the very first unsafe request from the SPA has
    # a token to echo (the frontend also lazily fetches /auth/csrf/).
    get_token(request)

    response = Response({"user": UserSerializer(user).data}, status=status.HTTP_200_OK)
    set_auth_cookies(response, refresh.access_token, refresh)
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """Logout endpoint — blacklist the refresh token(s) and clear cookies."""
    raw_cookie = request.COOKIES.get(REFRESH_COOKIE)
    candidates = [raw_cookie, request.data.get("refresh_token"), request.data.get("refresh")]

    for candidate in candidates:
        if not candidate:
            continue
        try:
            RefreshToken(candidate).blacklist()
        except TokenError:
            # Missing/expired/already-blacklisted: nothing to revoke.
            continue

    record_auth_event(request, AuthEvent.LOGOUT, user=request.user)
    response = Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
    clear_auth_cookies(response)
    return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh rotation that reads/writes the HttpOnly refresh cookie.

    * Cookie present → web flow: the refresh token is an ambient credential,
      so a valid CSRF token is required, and the rotated pair goes back into
      cookies (body stays empty).
    * No cookie → API/bearer flow: the classic ``{"refresh": "..."}`` body and
      ``{"access", "refresh"}`` response are unchanged.
    """

    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request, *args, **kwargs):
        cookie_token = request.COOKIES.get(REFRESH_COOKIE)
        if cookie_token:
            CookieJWTAuthentication.enforce_csrf(request)
            data = {"refresh": cookie_token}
        elif request.data.get("refresh"):
            data = {"refresh": request.data["refresh"]}
        else:
            raise AuthenticationFailed("No active session")

        serializer = TokenRefreshSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            # Expired/revoked refresh token: render as a clean 401.
            raise InvalidToken(str(exc)) from exc

        if not cookie_token:
            # Bearer client: hand the rotated pair back in the body.
            return Response(serializer.validated_data, status=status.HTTP_200_OK)

        response = Response({"detail": "Session refreshed"}, status=status.HTTP_200_OK)
        set_auth_cookies(
            response,
            serializer.validated_data["access"],
            serializer.validated_data["refresh"],
        )
        return response


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf_token(request):
    """Ensure the double-submit CSRF cookie exists and return nothing else.

    The frontend calls this before its first unsafe request when ``csrftoken``
    is missing (login also primes it).
    """
    get_token(request)
    return Response({"detail": "CSRF cookie set"}, status=status.HTTP_200_OK)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def profile(request):
    """Get or update user profile"""
    if request.method == "GET":
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    elif request.method == "PUT":
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "user": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@throttle_classes([ChangePasswordRateThrottle])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change user password.

    Every other session is revoked (blacklist all outstanding refresh tokens)
    and this device receives a fresh cookie pair.
    """
    serializer = PasswordChangeSerializer(data=request.data)
    if serializer.is_valid():
        user = request.user

        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"error": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        blacklist_all_tokens(user)
        refresh = RefreshToken.for_user(user)
        record_auth_event(request, AuthEvent.PASSWORD_CHANGED, user=user)

        response = Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)
        set_auth_cookies(response, refresh.access_token, refresh)
        return response

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AddressListCreateView(generics.ListCreateAPIView):
    """List and create addresses"""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete address"""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)
