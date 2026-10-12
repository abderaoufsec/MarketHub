"""Password recovery, end to end — Phase 8 of docs/todo.md.

Two paths, because Algeria is phone-first:

* **email** — forgot → link → reset (the classic flow, now with the SMTP
  outage made non-fatal: a dead mail server can never 500 an endpoint);
* **phone** — forgot → SMS code → reset, the only recovery a phone-only
  account has.

Both end with every other session revoked and a security notice sent.
"""

import re
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.sms import outbox
from tests.factories import PhoneOnlyUserFactory, UserFactory
from tests.helpers import last_sms_code

pytestmark = pytest.mark.django_db

FORGOT_URL = "/api/v1/auth/password/forgot/"
RESET_URL = "/api/v1/auth/password/reset/"
RESEND_URL = "/api/v1/auth/verify-email/resend/"
REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
OTP_URL = "/api/v1/auth/phone/otp/"
PHONE_RESET_URL = "/api/v1/auth/phone/reset/"

NEW_PASSWORD = "BrandNew!Pass9"
PHONE = "0555 12 34 56"
E164 = "+213555123456"


def _reset_params():
    """Read the ``uid``/``token`` out of the link the user would click."""
    body = mail.outbox[-1].body
    url = re.search(r"(https?://\S+/reset-password/\?\S+)", body).group(1)
    query = parse_qs(urlparse(url).query)
    return {"uid": query["uid"][0], "token": query["token"][0]}


# ---------------------------------------------------------------------------
# Email path
# ---------------------------------------------------------------------------
def test_forgot_password_sends_the_reset_link(api_client, buyer):
    response = api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert "/reset-password/" in mail.outbox[0].body
    assert "uid=" in mail.outbox[0].body
    assert "token=" in mail.outbox[0].body


def test_forgot_password_never_reveals_unknown_addresses(api_client):
    response = api_client.post(FORGOT_URL, {"email": "nobody@example.com"}, format="json")

    assert response.status_code == 200  # same reply as for a real address
    assert mail.outbox == []


def test_reset_password_completes_and_kills_old_sessions(api_client, buyer):
    old_refresh = str(RefreshToken.for_user(buyer))
    api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")

    response = api_client.post(
        RESET_URL,
        {
            **_reset_params(),
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.check_password(NEW_PASSWORD)
    # The security notice went out (non-fatal, but it is sent in-process).
    assert any("password was changed" in m.subject.lower() for m in mail.outbox)

    # Old password is dead, new one works, the old session is blacklisted.
    assert (
        api_client.post(
            LOGIN_URL, {"email": buyer.email, "password": "Str0ng!Passw0rd"}, format="json"
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            LOGIN_URL, {"email": buyer.email, "password": NEW_PASSWORD}, format="json"
        ).status_code
        == 200
    )
    from rest_framework.test import APIClient

    replay = APIClient().post(
        "/api/v1/auth/token/refresh/", {"refresh": old_refresh}, format="json"
    )
    assert replay.status_code == 401


def test_reset_password_rejects_a_tampered_token(api_client, buyer):
    api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")
    params = _reset_params()

    response = api_client.post(
        RESET_URL,
        {
            **params,
            "token": params["token"][:-1] + ("x" if params["token"][-1] != "x" else "y"),
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"
    buyer.refresh_from_db()
    assert buyer.check_password("Str0ng!Passw0rd")


def test_reset_password_rejects_unknown_uid(api_client):
    import base64

    response = api_client.post(
        RESET_URL,
        {
            "uid": base64.urlsafe_b64encode(b"999999").decode(),
            "token": "whatever",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400


def test_reset_password_rejects_mismatched_passwords(api_client, buyer):
    api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")

    response = api_client.post(
        RESET_URL,
        {**_reset_params(), "new_password": NEW_PASSWORD, "new_password_confirm": "Other!Pass9"},
        format="json",
    )

    assert response.status_code == 400
    buyer.refresh_from_db()
    assert buyer.check_password("Str0ng!Passw0rd")


def test_reset_token_cannot_be_reused(api_client, buyer):
    api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")
    params = _reset_params()
    body = {
        **params,
        "new_password": NEW_PASSWORD,
        "new_password_confirm": NEW_PASSWORD,
    }

    first = api_client.post(RESET_URL, body, format="json")
    second = api_client.post(RESET_URL, body, format="json")

    assert first.status_code == 200
    # Django's token generator invalidates after the password changes.
    assert second.status_code == 400


# ---------------------------------------------------------------------------
# Email delivery is never fatal (Phase 8 requirement)
# ---------------------------------------------------------------------------
@override_settings(EMAIL_BACKEND="tests.helpers.FailingEmailBackend")
def test_registration_survives_an_smtp_outage(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "outage@example.com",
            "username": "outage",
            "password": "S3cure!Passw0rd",
            "password_confirm": "S3cure!Passw0rd",
        },
        format="json",
    )

    assert response.status_code == 201  # not a 500
    assert "could not be sent" in response.data["message"]


@override_settings(EMAIL_BACKEND="tests.helpers.FailingEmailBackend")
def test_forgot_password_survives_an_smtp_outage(api_client, buyer):
    response = api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")

    assert response.status_code == 200


def test_reset_password_survives_an_smtp_outage(api_client, buyer):
    # The link itself was mailed before the outage; the completion and its
    # best-effort notice must still go through.
    api_client.post(FORGOT_URL, {"email": buyer.email}, format="json")
    params = _reset_params()

    with override_settings(EMAIL_BACKEND="tests.helpers.FailingEmailBackend"):
        response = api_client.post(
            RESET_URL,
            {**params, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
        )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.check_password(NEW_PASSWORD)


# ---------------------------------------------------------------------------
# Resend verification (the "email bounced" escape hatch)
# ---------------------------------------------------------------------------
def test_resend_verification_delivers_to_an_unverified_account(api_client):
    user = UserFactory(is_verified=False)

    response = api_client.post(RESEND_URL, {"email": user.email}, format="json")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert "/verify-email/" in mail.outbox[0].body


def test_resend_verification_is_generic_for_unknown_addresses(api_client):
    response = api_client.post(RESEND_URL, {"email": "ghost@example.com"}, format="json")

    assert response.status_code == 200
    assert mail.outbox == []


def test_resend_verification_skips_already_verified_accounts(api_client):
    user = UserFactory(is_verified=True)

    response = api_client.post(RESEND_URL, {"email": user.email}, format="json")

    assert response.status_code == 200
    assert mail.outbox == []


# ---------------------------------------------------------------------------
# Phone path — the only recovery a phone-only account has
# ---------------------------------------------------------------------------
def test_phone_reset_flow(api_client):
    user = PhoneOnlyUserFactory(phone_number=E164)

    requested = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "password_reset"}, format="json"
    )
    assert requested.status_code == 200
    code = last_sms_code()

    response = api_client.post(
        PHONE_RESET_URL,
        {
            "phone_number": PHONE,
            "code": code,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    # Change notice went out on the channel this account actually owns.
    assert any("password was changed" in m["message"].lower() for m in outbox)

    login = api_client.post(LOGIN_URL, {"email": PHONE, "password": NEW_PASSWORD}, format="json")
    assert login.status_code == 200


def test_phone_reset_refuses_an_unknown_number_without_spending_sms(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "password_reset"}, format="json"
    )
    assert response.status_code == 200
    assert outbox == []  # generic reply, and nobody paid for a message

    # Even a guessed code proves nothing when no code was ever issued.
    reset = api_client.post(
        PHONE_RESET_URL,
        {
            "phone_number": PHONE,
            "code": "123456",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )
    assert reset.status_code == 400


def test_phone_reset_rejects_a_wrong_code(api_client):
    user = PhoneOnlyUserFactory(phone_number=E164)
    api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "password_reset"}, format="json")

    response = api_client.post(
        PHONE_RESET_URL,
        {
            "phone_number": PHONE,
            "code": "000000",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("Str0ng!Passw0rd")
