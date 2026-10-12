"""Phone-first identity end-to-end — Phase 8 of docs/todo.md.

**Done when:** "a new user can register with just a phone, verify by OTP, log
in, and recover access end-to-end." Recovery itself lives in
``test_password_reset.py``; this file covers register-by-phone, login by
phone (password *and* OTP) and binding a number to an existing account.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.users.models import AuthEvent
from apps.users.otp import issue_otp
from apps.users.sms import outbox
from tests.factories import PhoneOnlyUserFactory, UserFactory
from tests.helpers import last_sms_code

User = get_user_model()

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
OTP_URL = "/api/auth/phone/otp/"
PHONE_LOGIN_URL = "/api/auth/phone/login/"
PHONE_VERIFY_URL = "/api/auth/phone/verify/"

VALID_PASSWORD = "Str0ng!Passw0rd"  # UserFactory's default raw password
PHONE = "0555 12 34 56"
E164 = "+213555123456"


def payload(**overrides):
    data = {
        "phone_number": PHONE,
        "password": VALID_PASSWORD,
        "password_confirm": VALID_PASSWORD,
        "first_name": "Ph",
        "last_name": "One",
    }
    data.update(overrides)
    return data


def request_register_code(api_client, phone=PHONE):
    response = api_client.post(
        OTP_URL, {"phone_number": phone, "purpose": "register"}, format="json"
    )
    assert response.status_code == 200, response.data
    return last_sms_code()


# ---------------------------------------------------------------------------
# Registration: phone + OTP, email optional
# ---------------------------------------------------------------------------
def test_register_with_only_a_phone_and_otp(api_client):
    code = request_register_code(api_client)

    response = api_client.post(REGISTER_URL, payload(otp_code=code), format="json")

    assert response.status_code == 201
    user = User.objects.get(phone_number=E164)
    assert user.email is None
    assert user.phone_verified is True
    assert user.is_verified is False  # no email to verify
    assert user.has_verified_identity() is True
    assert user.username  # auto-derived for phone-only accounts
    assert user.check_password(VALID_PASSWORD)

    # The code was single-use: it cannot register a second account.
    duplicate = api_client.post(REGISTER_URL, payload(otp_code=code), format="json")
    assert duplicate.status_code == 400
    assert User.objects.filter(phone_number=E164).count() == 1


def test_phone_only_registration_without_otp_is_refused(api_client):
    response = api_client.post(REGISTER_URL, payload(), format="json")

    assert response.status_code == 400
    assert "otp_code" in response.data
    assert not User.objects.filter(phone_number=E164).exists()


def test_registration_with_a_wrong_otp_never_creates_the_account(api_client):
    request_register_code(api_client)

    response = api_client.post(REGISTER_URL, payload(otp_code="000000"), format="json")

    assert response.status_code == 400
    assert "otp_code" in response.data
    assert not User.objects.filter(phone_number=E164).exists()


def test_email_registration_may_carry_an_unverified_phone(api_client):
    """No OTP → the number is stored for convenience but proves nothing yet
    (the profile gains it as unverified, Phase 17 upgrades tiers on top)."""
    response = api_client.post(
        REGISTER_URL,
        payload(email="withphone@example.com", username="withphone"),
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(email="withphone@example.com")
    assert user.phone_number == E164
    assert user.phone_verified is False
    assert user.is_verified is False


def test_registration_needs_email_or_phone(api_client):
    response = api_client.post(
        REGISTER_URL,
        payload(phone_number="", email=""),
        format="json",
    )

    assert response.status_code == 400
    assert "email" in response.data


def test_registration_rejects_a_malformed_phone(api_client):
    response = api_client.post(REGISTER_URL, payload(phone_number="call-me-maybe"), format="json")

    assert response.status_code == 400
    assert "phone_number" in response.data


def test_registration_cannot_claim_an_already_verified_number(api_client):
    PhoneOnlyUserFactory(phone_number=E164)
    # The request endpoint refuses (see test_otp), but the serializer must
    # too: possession of a code for somebody else's number is not ownership.
    issue_otp(phone_number=E164, purpose="register")
    code = last_sms_code()

    response = api_client.post(
        REGISTER_URL,
        payload(email="squat@example.com", username="squat", otp_code=code),
        format="json",
    )

    assert response.status_code == 400
    assert "phone_number" in response.data


def test_username_collisions_are_resolved_automatically(api_client):
    UserFactory(email="ph@example.com", username="ph")
    code = request_register_code(api_client)

    response = api_client.post(REGISTER_URL, payload(otp_code=code), format="json")

    assert response.status_code == 201
    user = User.objects.get(phone_number=E164)
    assert user.username != "ph"
    assert User.objects.filter(username=user.username).count() == 1


# ---------------------------------------------------------------------------
# Login: email *or* phone identifier
# ---------------------------------------------------------------------------
def test_login_with_phone_number_and_password(api_client):
    PhoneOnlyUserFactory(phone_number=E164)

    response = api_client.post(
        LOGIN_URL,
        {"email": PHONE, "password": VALID_PASSWORD},  # the field now takes both
        format="json",
    )

    assert response.status_code == 200
    assert response.data["user"]["phone_number"] == E164
    assert response.cookies["access_token"]["httponly"]


def test_login_with_wrong_phone_password_is_401(api_client):
    PhoneOnlyUserFactory(phone_number=E164)

    response = api_client.post(
        LOGIN_URL, {"email": PHONE, "password": "WrongPass!1"}, format="json"
    )

    assert response.status_code == 401


def test_unverified_phone_does_not_unlock_login(api_client):
    """A number bound without proving control (profile PUT) is not identity."""
    UserFactory(
        email=None,
        is_verified=False,
        phone_number=E164,
        phone_verified_at=None,
    )

    response = api_client.post(
        LOGIN_URL, {"email": PHONE, "password": VALID_PASSWORD}, format="json"
    )

    assert response.status_code == 401


def test_verified_phone_unlocks_an_emailless_account_after_email_check(api_client):
    """The old gate was email-only; Phase 8 accepts *either* proven identity."""
    user = PhoneOnlyUserFactory(phone_number=E164)
    assert user.is_verified is False

    response = api_client.post(
        LOGIN_URL, {"email": PHONE, "password": VALID_PASSWORD}, format="json"
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Passwordless login: OTP
# ---------------------------------------------------------------------------
def test_otp_login_flow(api_client):
    user = PhoneOnlyUserFactory(phone_number=E164)

    request = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")
    assert request.status_code == 200
    code = last_sms_code()

    response = api_client.post(
        PHONE_LOGIN_URL, {"phone_number": PHONE, "code": code}, format="json"
    )

    assert response.status_code == 200
    assert response.data["user"]["id"] == user.id
    assert response.cookies["access_token"]["httponly"]
    assert response.cookies["mh_session"].value == "1"

    # Audited with the method that got us in.
    event = AuthEvent.objects.get(event=AuthEvent.LOGIN_SUCCESS, user=user)
    assert event.details["method"] == "phone_otp"


def test_otp_login_rejects_a_wrong_code(api_client):
    PhoneOnlyUserFactory(phone_number=E164)
    api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")

    response = api_client.post(
        PHONE_LOGIN_URL, {"phone_number": PHONE, "code": "000000"}, format="json"
    )

    assert response.status_code == 400
    assert "error" in response.data


def test_disabled_account_never_receives_a_login_code(api_client):
    user = PhoneOnlyUserFactory(phone_number=E164, is_active=False)

    response = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")

    assert response.status_code == 200  # generic reply, no enumeration
    assert outbox == []
    assert user.is_active is False


# ---------------------------------------------------------------------------
# Binding a number to an existing account (authenticated)
# ---------------------------------------------------------------------------
def test_user_verifies_their_phone_from_the_profile(buyer_client, buyer):
    response = buyer_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "phone_change"}, format="json"
    )
    assert response.status_code == 200
    code = last_sms_code()

    verified = buyer_client.post(
        PHONE_VERIFY_URL, {"phone_number": PHONE, "code": code}, format="json"
    )

    assert verified.status_code == 200
    buyer.refresh_from_db()
    assert buyer.phone_number == E164
    assert buyer.phone_verified is True
    assert verified.data["user"]["phone_verified"] is True
    assert AuthEvent.objects.filter(event=AuthEvent.PHONE_VERIFIED, user=buyer).exists()


def test_cannot_bind_a_number_verified_on_another_account(buyer_client):
    holder = PhoneOnlyUserFactory(phone_number="+213555000002")

    response = buyer_client.post(
        OTP_URL,
        {"phone_number": holder.phone_number, "purpose": "phone_change"},
        format="json",
    )

    assert response.status_code == 400
    assert outbox == []


def test_cannot_request_a_second_code_for_own_verified_number(buyer_client, buyer):
    buyer.phone_number = E164
    buyer.phone_verified_at = buyer.date_joined
    buyer.save()

    response = buyer_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "phone_change"}, format="json"
    )

    assert response.status_code == 400
    assert outbox == []


def test_verify_endpoint_rejects_a_wrong_code(buyer_client, buyer):
    buyer_client.post(OTP_URL, {"phone_number": PHONE}, format="json")

    response = buyer_client.post(
        PHONE_VERIFY_URL, {"phone_number": PHONE, "code": "000000"}, format="json"
    )

    assert response.status_code == 400
    buyer.refresh_from_db()
    assert buyer.phone_verified is False


@override_settings(SMS_BACKEND="tests.helpers.FailingSmsBackend")
def test_sms_outage_does_not_half_verify_anything(buyer_client, buyer):
    response = buyer_client.post(OTP_URL, {"phone_number": PHONE}, format="json")

    assert response.status_code == 503
    buyer.refresh_from_db()
    assert buyer.phone_number in (None, "")
    assert buyer.phone_verified is False
