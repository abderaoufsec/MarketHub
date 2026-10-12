"""Registration, login, logout and email-verification flows."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from tests.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
REFRESH_URL = "/api/auth/token/refresh/"
PROFILE_URL = "/api/auth/profile/"

VALID_PASSWORD = "S3cure!Passw0rd"


def registration_payload(**overrides):
    data = {
        "email": "newbie@example.com",
        "username": "newbie",
        "password": VALID_PASSWORD,
        "password_confirm": VALID_PASSWORD,
        "first_name": "New",
        "last_name": "User",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_creates_unverified_user(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(), format="json")

    assert response.status_code == 201
    assert response.data["user"]["email"] == "newbie@example.com"
    user = User.objects.get(email="newbie@example.com")
    assert user.is_verified is False
    assert user.check_password(VALID_PASSWORD)


def test_register_rejects_mismatched_passwords(api_client):
    response = api_client.post(
        REGISTER_URL,
        registration_payload(password_confirm="Different!Pass1"),
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="newbie@example.com").exists()


def test_register_rejects_duplicate_email(api_client):
    UserFactory(email="taken@example.com")

    response = api_client.post(
        REGISTER_URL, registration_payload(email="taken@example.com"), format="json"
    )

    assert response.status_code == 400
    assert "email" in response.data


def test_register_rejects_weak_password(api_client):
    response = api_client.post(
        REGISTER_URL,
        registration_payload(password="123", password_confirm="123"),
        format="json",
    )

    assert response.status_code == 400
    assert "password" in response.data


def test_registration_sends_exactly_one_verification_email(api_client):
    """Phase 8 fix: the duplicate ``post_save`` receiver is deleted — one
    registration, one email, one flow (the old one emailed a raw-uuid link no
    view ever accepted)."""
    before = len(mail.outbox)

    response = api_client.post(REGISTER_URL, registration_payload(), format="json")

    assert response.status_code == 201
    assert len(mail.outbox) - before == 1


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
def test_login_returns_user_and_httponly_cookies(api_client):
    user = UserFactory(email="login@example.com")

    response = api_client.post(
        LOGIN_URL,
        {"email": "login@example.com", "password": "Str0ng!Passw0rd"},
        format="json",
    )

    assert response.status_code == 200
    # Phase 7: tokens never appear in the response body (an XSS hook must not
    # be able to read them); they live in HttpOnly cookies.
    assert "access" not in response.data
    assert "refresh" not in response.data
    assert response.data["user"]["email"] == user.email
    assert response.cookies["access_token"]["httponly"]
    assert response.cookies["refresh_token"]["httponly"]
    # Readable session flag + primed CSRF cookie for the SPA's first write.
    assert response.cookies["mh_session"].value == "1"
    assert "csrftoken" in response.cookies


def test_cookie_session_can_call_profile(api_client):
    UserFactory(email="cookie@example.com")
    login = api_client.post(
        LOGIN_URL,
        {"email": "cookie@example.com", "password": "Str0ng!Passw0rd"},
        format="json",
    )
    assert login.status_code == 200

    profile = api_client.get("/api/auth/profile/")

    assert profile.status_code == 200
    assert profile.data["email"] == "cookie@example.com"


def test_bearer_header_still_authenticates_without_csrf(api_client):
    """API/mobile clients keep the Authorization: Bearer flow (no CSRF)."""
    from rest_framework_simplejwt.tokens import RefreshToken

    user = UserFactory(email="bearer@example.com")
    token = str(RefreshToken.for_user(user).access_token)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    profile = api_client.get("/api/auth/profile/")
    write = api_client.put(
        "/api/auth/profile/", {"first_name": "B"}, format="json"
    )  # no X-CSRFToken: bearer requests are exempt

    assert profile.status_code == 200
    assert write.status_code == 200


def test_login_rejected_for_unverified_user(api_client):
    UserFactory(email="pending@example.com", is_verified=False)

    response = api_client.post(
        LOGIN_URL,
        {"email": "pending@example.com", "password": "Str0ng!Passw0rd"},
        format="json",
    )

    assert response.status_code == 403


def test_login_rejects_wrong_password(api_client):
    UserFactory(email="login@example.com")

    response = api_client.post(
        LOGIN_URL,
        {"email": "login@example.com", "password": "WrongPass!1"},
        format="json",
    )

    assert response.status_code == 401


def test_login_requires_credentials(api_client):
    response = api_client.post(LOGIN_URL, {"email": "someone@example.com"}, format="json")

    assert response.status_code == 400


def test_logout_blacklists_refresh_token(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    user = UserFactory()
    api_client.force_authenticate(user=user)
    refresh = RefreshToken.for_user(user)

    response = api_client.post(LOGOUT_URL, {"refresh_token": str(refresh)}, format="json")
    assert response.status_code == 200

    replay = api_client.post(REFRESH_URL, {"refresh": str(refresh)}, format="json")
    assert replay.status_code == 401


def test_logout_clears_the_session_cookies(api_client):
    user = UserFactory(email="bye@example.com")
    login = api_client.post(
        LOGIN_URL, {"email": "bye@example.com", "password": "Str0ng!Passw0rd"}, format="json"
    )
    assert login.status_code == 200

    response = api_client.post(LOGOUT_URL, {}, format="json")

    assert response.status_code == 200
    # Deleted cookies come back with an expiry in the past.
    assert response.cookies["access_token"].value == ""
    assert response.cookies["refresh_token"].value == ""
    assert response.cookies["mh_session"].value == ""
    # and the session is gone
    assert api_client.get("/api/auth/profile/").status_code == 401


def test_logout_without_session_is_rejected(api_client):
    response = api_client.post(LOGOUT_URL, {}, format="json")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cookie refresh + CSRF (Phase 7)
# ---------------------------------------------------------------------------
def test_cookie_refresh_rotates_the_pair_without_a_body(api_client):
    user = UserFactory(email="rotate@example.com")
    login = api_client.post(
        LOGIN_URL, {"email": "rotate@example.com", "password": "Str0ng!Passw0rd"}, format="json"
    )
    assert login.status_code == 200
    first_access = api_client.cookies["access_token"].value

    response = api_client.post(REFRESH_URL, {}, format="json")

    assert response.status_code == 200
    assert "access" not in response.data
    assert "refresh" not in response.data
    assert api_client.cookies["access_token"].value
    assert api_client.cookies["access_token"].value != first_access
    # The rotated pair keeps working against a protected endpoint.
    assert api_client.get("/api/auth/profile/").status_code == 200


def test_cookie_refresh_without_session_is_rejected(api_client):
    response = api_client.post(REFRESH_URL, {}, format="json")
    assert response.status_code == 401


def test_cookie_authenticated_write_requires_csrf():
    from rest_framework.test import APIClient

    client = APIClient(enforce_csrf_checks=True)
    UserFactory(email="csrf@example.com")
    login = client.post(
        LOGIN_URL, {"email": "csrf@example.com", "password": "Str0ng!Passw0rd"}, format="json"
    )
    assert login.status_code == 200
    csrf_token = client.cookies["csrftoken"].value

    # 1. unsafe request authenticated by cookie, no X-CSRFToken -> rejected
    rejected = client.put(
        PROFILE_URL,
        {"first_name": "Nope"},
        format="json",
        HTTP_ORIGIN="http://testserver",
    )
    assert rejected.status_code == 403
    assert "CSRF" in str(rejected.data.get("detail", ""))

    # 2. same request with the double-submit header -> accepted
    accepted = client.put(
        PROFILE_URL,
        {"first_name": "Yes"},
        format="json",
        HTTP_ORIGIN="http://testserver",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert accepted.status_code == 200


def test_csrf_endpoint_sets_the_cookie(api_client):
    response = api_client.get("/api/auth/csrf/")

    assert response.status_code == 200
    assert "csrftoken" in response.cookies


# ---------------------------------------------------------------------------
# Brute force: failed-login backoff + throttling (Phase 7)
# ---------------------------------------------------------------------------
def test_failed_logins_lock_out_the_pair(api_client):
    from django.core.cache import cache

    from apps.users.security import LOGIN_FAIL_THRESHOLD

    UserFactory(email="victim@example.com")
    for _ in range(LOGIN_FAIL_THRESHOLD):
        failed = api_client.post(
            LOGIN_URL,
            {"email": "victim@example.com", "password": "WrongPass!1"},
            format="json",
        )
        assert failed.status_code == 401

    # Even the *correct* password is refused while the lockout holds.
    locked = api_client.post(
        LOGIN_URL,
        {"email": "victim@example.com", "password": "Str0ng!Passw0rd"},
        format="json",
    )
    assert locked.status_code == 429

    cache.clear()  # lockout expired
    recovered = api_client.post(
        LOGIN_URL,
        {"email": "victim@example.com", "password": "Str0ng!Passw0rd"},
        format="json",
    )
    assert recovered.status_code == 200


def test_successful_login_wipes_the_backoff_state(api_client):
    from django.core.cache import cache

    from apps.users.security import LOGIN_FAIL_THRESHOLD, _key

    UserFactory(email="reset@example.com")
    for _ in range(LOGIN_FAIL_THRESHOLD - 1):
        api_client.post(
            LOGIN_URL, {"email": "reset@example.com", "password": "WrongPass!1"}, format="json"
        )

    assert cache.get(_key("127.0.0.1", "reset@example.com")) is not None
    ok = api_client.post(
        LOGIN_URL, {"email": "reset@example.com", "password": "Str0ng!Passw0rd"}, format="json"
    )
    assert ok.status_code == 200
    assert cache.get(_key("127.0.0.1", "reset@example.com")) is None


def test_login_is_rate_limited():
    from rest_framework.test import APIClient

    from tests.helpers import throttle_rate

    UserFactory(email="burst@example.com")
    client = APIClient()
    # Failed attempts never receive cookies, so the throttle key stays the
    # caller's IP — exactly the brute-force pattern this protects against.
    with throttle_rate("login", "3/min"):
        codes = [
            client.post(
                LOGIN_URL,
                {"email": "burst@example.com", "password": "WrongPass!1"},
                format="json",
            ).status_code
            for _ in range(5)
        ]

    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


def test_register_is_rate_limited():
    from rest_framework.test import APIClient

    from tests.helpers import throttle_rate

    client = APIClient()
    with throttle_rate("register", "2/hour"):
        codes = [
            client.post(REGISTER_URL, registration_payload(), format="json").status_code
            for _ in range(3)
        ]

    # 201/400 for the first two attempts, 429 for the third.
    assert codes[2] == 429


# ---------------------------------------------------------------------------
# Auth audit log (Phase 7)
# ---------------------------------------------------------------------------
def test_login_and_logout_are_audited(api_client):
    from apps.users.models import AuthEvent

    UserFactory(email="audited@example.com")
    api_client.post(
        LOGIN_URL, {"email": "audited@example.com", "password": "Str0ng!Passw0rd"}, format="json"
    )
    api_client.post(LOGOUT_URL, {}, format="json")

    events = list(
        AuthEvent.objects.filter(email="audited@example.com").values_list("event", flat=True)
    )
    assert AuthEvent.LOGIN_SUCCESS in events
    assert AuthEvent.LOGOUT in events


def test_failed_login_is_audited_with_the_ip(api_client):
    from apps.users.models import AuthEvent

    UserFactory(email="miss@example.com")
    api_client.post(
        LOGIN_URL, {"email": "miss@example.com", "password": "Nope!Pass1"}, format="json"
    )

    event = AuthEvent.objects.get(event=AuthEvent.LOGIN_FAILED, email="miss@example.com")
    assert event.user is None
    assert event.ip == "127.0.0.1"
    assert event.details["reason"] == "invalid_credentials"


def test_registration_is_audited(api_client):
    from apps.users.models import AuthEvent

    api_client.post(REGISTER_URL, registration_payload(), format="json")

    assert AuthEvent.objects.filter(event=AuthEvent.REGISTERED, email="newbie@example.com").exists()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------
def _verification_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"/api/auth/verify-email/{uid}/{token}/"


def test_verify_email_marks_user_verified(api_client):
    user = UserFactory(is_verified=False)

    response = api_client.get(_verification_url(user))

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_verified is True


def test_verify_email_rejects_invalid_token(api_client):
    user = UserFactory(is_verified=False)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    response = api_client.get(f"/api/auth/verify-email/{uid}/not-a-real-token/")

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_verified is False


def test_verify_email_rejects_unknown_uid(api_client):
    uid = urlsafe_base64_encode(force_bytes(999999))

    response = api_client.get(f"/api/auth/verify-email/{uid}/whatever/")

    assert response.status_code == 400
