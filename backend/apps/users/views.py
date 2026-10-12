from contextlib import suppress

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
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
from .email import (
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
)
from .models import Address, AuthEvent, User
from .otp import OtpError, clear_budgets, issue_otp, verify_otp
from .phones import is_phone_like, mask_phone, normalize_phone
from .security import check_login_backoff, clear_login_failures, record_login_failure
from .serializers import (
    AddressSerializer,
    ForgotPasswordSerializer,
    PasswordChangeSerializer,
    PhoneLoginSerializer,
    PhoneOtpRequestSerializer,
    PhonePasswordResetSerializer,
    PhoneVerifySerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    SocialLoginSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)
from .sms import SmsError, send_sms
from .social import SocialError, get_social_profile
from .throttles import (
    ChangePasswordRateThrottle,
    ForgotPasswordRateThrottle,
    LoginRateThrottle,
    OtpRequestRateThrottle,
    OtpVerifyRateThrottle,
    RegisterRateThrottle,
    ResendVerificationRateThrottle,
    SocialLoginRateThrottle,
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


def _start_session(request, user, *, method: str, **audit_details) -> Response:
    """Issue the HttpOnly cookie pair for ``user``.

    Shared by every sign-in path (password, phone OTP, social) so the
    session, CSRF priming and audit behaviour can never drift apart. Also the
    single place ``last_login`` is stamped: SimpleJWT only writes it inside
    its own obtain/refresh serializers, which none of these flows use — so
    the setting was on but nothing was updating it.
    """
    refresh = RefreshToken.for_user(user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    record_auth_event(request, AuthEvent.LOGIN_SUCCESS, user=user, method=method, **audit_details)
    # Prime the CSRF cookie so the very first unsafe request from the SPA has
    # a token to echo (the frontend also lazily fetches /auth/csrf/).
    get_token(request)

    response = Response({"user": UserSerializer(user).data}, status=status.HTTP_200_OK)
    set_auth_cookies(response, refresh.access_token, refresh)
    return response


# ---------------------------------------------------------------------------
# Registration & email verification (Phase 8: one flow, phone-first)
# ---------------------------------------------------------------------------
@api_view(["POST"])
@throttle_classes([RegisterRateThrottle])
@permission_classes([AllowAny])
def register(request):
    """Create an account.

    Phase 8 of docs/todo.md: **one** verification flow — the duplicate
    ``post_save`` receiver that also emailed a link (a link no view ever
    accepted) is gone, and delivery is non-fatal: an SMTP outage can never
    turn a successful sign-up into a 500. Sign-up works with an email, with a
    phone number + OTP, or both.
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    email_sent = bool(user.email) and send_verification_email(user)

    record_auth_event(request, AuthEvent.REGISTERED, user=user, is_seller=user.is_seller)

    if user.has_verified_identity():
        message = "Registration successful. Your account is ready to use."
    elif email_sent:
        message = "Registration successful. Please check your email to verify your account."
    else:
        message = (
            "Registration successful, but the verification email could not be "
            'sent. Use "resend verification" to try again.'
        )

    return Response(
        {"message": message, "user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )


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
        if not user.is_verified:
            user.is_verified = True
            user.save(update_fields=["is_verified"])
        record_auth_event(request, AuthEvent.EMAIL_VERIFIED, user=user)
        return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)

    return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@throttle_classes([ResendVerificationRateThrottle])
@permission_classes([AllowAny])
def resend_verification(request):
    """Send another verification link. Always answers 200 — the reply must not
    reveal whether an address is registered (enumeration)."""
    serializer = ResendVerificationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=serializer.validated_data["email"]).first()
    if user and not user.is_verified:
        # Non-fatal: SMTP outage logs server-side, reply stays identical.
        send_verification_email(user)

    return Response(
        {"detail": "If that account still needs verification, a new link is on its way."},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Password recovery by email (Phase 8)
# ---------------------------------------------------------------------------
@api_view(["POST"])
@throttle_classes([ForgotPasswordRateThrottle])
@permission_classes([AllowAny])
def forgot_password(request):
    """Request a reset link. Enumeration-safe: always 200, and an unknown
    address simply sends nothing."""
    serializer = ForgotPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=serializer.validated_data["email"]).first()
    if user:
        send_password_reset_email(user)
        record_auth_event(request, AuthEvent.PASSWORD_RESET, user=user, via="email")

    return Response(
        {"detail": "If that address has an account, a reset link is on its way."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@throttle_classes([ForgotPasswordRateThrottle])
@permission_classes([AllowAny])
def reset_password(request):
    """Consume the emailed ``uid``/``token`` pair and set a new password.

    On success every other session is revoked (stolen-token posture) and a
    security notice is sent — non-fatal, like every other send.
    """
    serializer = ResetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        uid = force_str(urlsafe_base64_decode(data["uid"]))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"error": "Invalid or expired reset link"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(user, data["token"]):
        return Response(
            {"error": "Invalid or expired reset link"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(data["new_password"])
    user.save(update_fields=["password"])
    blacklist_all_tokens(user)
    record_auth_event(request, AuthEvent.PASSWORD_RESET, user=user, via="email_link")
    send_password_changed_email(user)

    return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Login / logout (Phase 8: email *or* phone identifier)
# ---------------------------------------------------------------------------
def _login_failure(request, identifier, *, reason, detail):
    record_login_failure(request, identifier)
    record_auth_event(request, AuthEvent.LOGIN_FAILED, email=identifier, reason=reason)
    return Response({"error": detail}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(["POST"])
@throttle_classes([LoginRateThrottle])
@permission_classes([AllowAny])
def login(request):
    """Login endpoint.

    ``email`` accepts an email address **or** a phone number (Phase 8 —
    phone-first accounts exist). The JWT pair is set as **HttpOnly cookies**
    and never appears in the response body (an XSS hook cannot read it out of
    a response it did not intercept live). Failed attempts feed the
    per-(IP, identifier) backoff in ``security.py``.
    """
    identifier = (
        request.data.get("email")
        or request.data.get("identifier")
        or request.data.get("phone_number")
    )
    password = request.data.get("password")

    if not identifier or not password:
        return Response(
            {"error": "Please provide both email and password"}, status=status.HTTP_400_BAD_REQUEST
        )

    check_login_backoff(request, identifier)

    if is_phone_like(identifier):
        # Phone + password. The number must be the *verified* one on the
        # account — an unverified number proves nothing about its holder.
        try:
            phone = normalize_phone(identifier)
        except Exception:  # malformed input == no such account
            phone = ""
        user = User.objects.filter(phone_number=phone, phone_verified_at__isnull=False).first()
        if user is None or not user.is_active or not user.check_password(password):
            return _login_failure(
                request,
                identifier,
                reason="invalid_credentials",
                detail="Invalid credentials",
            )
    else:
        user = authenticate(username=identifier, password=password)
        if user is None:
            return _login_failure(
                request,
                identifier,
                reason="invalid_credentials",
                detail="Invalid credentials",
            )

    if not user.has_verified_identity():
        record_auth_event(
            request,
            AuthEvent.LOGIN_FAILED,
            user=user,
            reason="identity_not_verified",
        )
        detail = (
            "Please verify your email before logging in"
            if user.email
            else "Please verify your phone number before logging in"
        )
        return Response({"error": detail}, status=status.HTTP_403_FORBIDDEN)

    clear_login_failures(request, identifier)
    method = "phone_password" if is_phone_like(identifier) else "password"
    return _start_session(request, user, method=method)


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


# ---------------------------------------------------------------------------
# Phone OTP (Phase 8 — SMS verification, the Algerian primary identity)
# ---------------------------------------------------------------------------
_OTP_GENERIC_DETAIL = "If that number can receive codes, one is on its way."
_OTP_NOT_FOUND = {"phone_number": ["This phone number is already registered."]}


@api_view(["POST"])
@throttle_classes([OtpRequestRateThrottle])
@permission_classes([AllowAny])
def phone_otp_request(request):
    """Send an SMS code (``POST /api/auth/phone/otp/``).

    Purposes:

    * ``register`` — claim a number during sign-up (400 if it is already
      registered: an honest answer the other purposes must not give).
    * ``login`` / ``password_reset`` — send **only when a verified binding
      exists**, but answer 200 either way: "no such account" is an oracle for
      probing harvested number lists.
    * ``phone_change`` — authenticated users only (attach/replace the number
      on their own account).

    Every send that actually happens goes through ``otp.issue_otp``, which
    enforces the cooldown and the per-number/per-IP daily budgets *before*
    the provider is paid (SMS pumping defence).
    """
    serializer = PhoneOtpRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    phone = serializer.validated_data["phone_number"]
    requested_purpose = serializer.validated_data["purpose"]
    authenticated = bool(request.user and request.user.is_authenticated)

    if authenticated:
        purpose = "phone_change"
        user = request.user
        if user.phone_number == phone and user.phone_verified:
            return Response(
                {"phone_number": ["This phone number is already verified."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            User.objects.filter(phone_number=phone, phone_verified_at__isnull=False)
            .exclude(pk=user.pk)
            .exists()
        ):
            return Response(_OTP_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)
        send = True
    else:
        purpose = requested_purpose
        if purpose == "phone_change":
            return Response(
                {"detail": "Sign in to verify the phone number on your account."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if purpose == "register":
            if User.objects.filter(phone_number=phone, phone_verified_at__isnull=False).exists():
                return Response(_OTP_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)
            user = None
            send = True
        else:  # login / password_reset — never confirm or deny an account.
            user = User.objects.filter(
                phone_number=phone, phone_verified_at__isnull=False, is_active=True
            ).first()
            send = user is not None

    if not send:
        return Response({"detail": _OTP_GENERIC_DETAIL}, status=status.HTTP_200_OK)

    try:
        issue_otp(
            phone_number=phone,
            purpose=purpose,
            user=user,
            ip=request.META.get("REMOTE_ADDR") or None,
        )
    except SmsError:
        # The user is waiting for a code that will never arrive: say so
        # instead of pretending (503 = try again shortly).
        return Response(
            {"detail": "SMS delivery is temporarily unavailable. Try again shortly."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"detail": _OTP_GENERIC_DETAIL}, status=status.HTTP_200_OK)


@api_view(["POST"])
@throttle_classes([OtpVerifyRateThrottle])
@permission_classes([AllowAny])
def phone_login(request):
    """Passwordless sign-in: the latest code for a verified number is the
    credential (``POST /api/auth/phone/login/``)."""
    serializer = PhoneLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        row = verify_otp(phone_number=data["phone_number"], purpose="login", code=data["code"])
    except OtpError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user = row.user
    if user is None or not user.is_active:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    clear_login_failures(request, data["phone_number"])
    clear_budgets(phone=data["phone_number"])
    return _start_session(request, user, method="phone_otp")


@api_view(["POST"])
@throttle_classes([OtpVerifyRateThrottle])
@permission_classes([AllowAny])
def phone_reset_password(request):
    """Recover access by SMS code (``POST /api/auth/phone/reset/``) — the
    only recovery path a phone-only account has.

    On success every session is revoked and a change notice is sent on every
    channel the account owns (best-effort)."""
    serializer = PhonePasswordResetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        row = verify_otp(
            phone_number=data["phone_number"], purpose="password_reset", code=data["code"]
        )
    except OtpError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user = row.user
    if user is None or not user.is_active:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    user.set_password(data["new_password"])
    user.save(update_fields=["password"])
    blacklist_all_tokens(user)
    record_auth_event(request, AuthEvent.PASSWORD_RESET, user=user, via="phone_otp")
    clear_budgets(phone=data["phone_number"])
    send_password_changed_email(user)
    # Change notice is best-effort; the reset itself already succeeded.
    with suppress(SmsError, TypeError, ValueError):
        send_sms(user.phone_number, "Your MarketHub password was changed.")

    return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)


@api_view(["POST"])
@throttle_classes([OtpVerifyRateThrottle])
@permission_classes([IsAuthenticated])
def phone_verify(request):
    """Authenticated: verify the phone number on your own account
    (``POST /api/auth/phone/verify/``). Binds the number and stamps
    ``phone_verified_at`` — the moment the account gains its primary
    identity."""
    serializer = PhoneVerifySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        row = verify_otp(
            phone_number=data["phone_number"], purpose="phone_change", code=data["code"]
        )
    except OtpError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    user.phone_number = row.phone_number
    user.phone_verified_at = row.consumed_at
    try:
        user.save(update_fields=["phone_number", "phone_verified_at"])
    except Exception:  # racing another account for the number
        return Response(_OTP_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)

    record_auth_event(
        request, AuthEvent.PHONE_VERIFIED, user=user, phone=mask_phone(row.phone_number)
    )
    clear_budgets(phone=row.phone_number)
    return Response(
        {"message": "Phone number verified", "user": UserSerializer(user).data},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Social login (Phase 8 — optional Google / Facebook)
# ---------------------------------------------------------------------------
@api_view(["POST"])
@throttle_classes([SocialLoginRateThrottle])
@permission_classes([AllowAny])
def social_login(request):
    """Sign in with a Google ID token or Facebook access token.

    The token is replayed to the issuer and verified **server-side**
    (audience, issuer, email_verified / debug_token) — the browser's word is
    never taken for it. A provider-verified email is a verified identity, so
    the account it creates can log in immediately."""
    serializer = SocialLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        profile = get_social_profile(data["provider"], data["access_token"])
    except SocialError as exc:
        return Response({"error": str(exc)}, status=exc.status)

    email = profile.email.lower()
    user = User.objects.filter(email=email).first()
    created = False
    if user is None:
        username = UserRegistrationSerializer._derive_username(email, None)
        username = UserRegistrationSerializer._unique_username(username)
        user = User.objects.create_user(
            email=email,
            username=username,
            password=None,  # unusable: this account can only sign in socially
            first_name=profile.first_name,
            last_name=profile.last_name,
        )
        created = True
    elif not user.is_active:
        return Response(
            {"error": "This account has been disabled."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not user.is_verified:
        # The provider vouched for the address (its email_verified /
        # debug_token checks above), so this *is* an email verification.
        user.is_verified = True
        user.save(update_fields=["is_verified"])

    return _start_session(
        request,
        user,
        method=data["provider"],
        provider=data["provider"],
        created=created,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
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
