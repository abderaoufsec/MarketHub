"""Phone OTP issuing/verification and SMS-pumping defence — Phase 8.

Covers the three properties that make an SMS code a credential: hard to
guess, short-lived/single-use, and expensive to pump (cooldown + per-number
and per-IP daily budgets, before any provider is paid).
"""

import re
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import Throttled

from apps.users.models import PhoneOtp, User
from apps.users.otp import OtpError, issue_otp, verify_otp
from apps.users.sms import SmsError, outbox
from tests.factories import PhoneOnlyUserFactory
from tests.helpers import last_sms_code

pytestmark = pytest.mark.django_db

OTP_URL = "/api/v1/auth/phone/otp/"
PHONE = "0555123456"
E164 = "+213555123456"


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------
def test_issue_then_verify_roundtrip():
    row = issue_otp(phone_number=PHONE, purpose="register")

    assert row.phone_number == E164
    assert outbox[-1]["phone_number"] == E164
    code = last_sms_code()
    assert code and len(code) == 6

    used = verify_otp(phone_number=E164, purpose="register", code=code)
    assert used.pk == row.pk
    used.refresh_from_db()
    assert used.consumed_at is not None

    # Single use: the same code cannot be replayed.
    with pytest.raises(OtpError):
        verify_otp(phone_number=E164, purpose="register", code=code)


def test_wrong_codes_burn_attempts_until_the_code_is_dead():
    from django.conf import settings

    row = issue_otp(phone_number=PHONE, purpose="register")
    code = last_sms_code()
    wrong = "999999" if code != "999999" else "888888"

    for attempt in range(settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(OtpError):
            verify_otp(phone_number=E164, purpose="register", code=wrong)
        row.refresh_from_db()
        assert row.attempts == attempt + 1

    # Even the genuine code is refused once the attempt cap is spent —
    # the 6-digit space never gets to be brute-forced.
    with pytest.raises(OtpError):
        verify_otp(phone_number=E164, purpose="register", code=code)


def test_expired_code_is_refused():
    row = issue_otp(phone_number=PHONE, purpose="register")
    code = last_sms_code()
    PhoneOtp.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    with pytest.raises(OtpError):
        verify_otp(phone_number=E164, purpose="register", code=code)


def test_unknown_phone_has_no_code_to_verify():
    issue_otp(phone_number=PHONE, purpose="register")

    with pytest.raises(OtpError):
        verify_otp(phone_number=E164, purpose="login", code=last_sms_code())


@override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
def test_a_new_code_invalidates_the_previous_one():
    old = issue_otp(phone_number=PHONE, purpose="register")
    old_code = last_sms_code()
    new = issue_otp(phone_number=PHONE, purpose="register")
    new_code = last_sms_code()

    old.refresh_from_db()
    assert old.consumed_at is not None  # superseded rows are dead
    with pytest.raises(OtpError):
        verify_otp(phone_number=E164, purpose="register", code=old_code)
    assert verify_otp(phone_number=E164, purpose="register", code=new_code).pk == new.pk


@override_settings(OTP_MAX_PER_PHONE_PER_DAY=2, OTP_RESEND_COOLDOWN_SECONDS=0)
def test_daily_budget_per_number_caps_sends():
    issue_otp(phone_number=PHONE, purpose="register")
    issue_otp(phone_number=PHONE, purpose="login")  # budget is per number, not per purpose

    with pytest.raises(Throttled):
        issue_otp(phone_number=PHONE, purpose="password_reset")


@override_settings(OTP_MAX_PER_IP_PER_DAY=1, OTP_RESEND_COOLDOWN_SECONDS=0)
def test_daily_budget_per_ip_caps_sends_across_numbers():
    issue_otp(phone_number=PHONE, purpose="register", ip="196.1.55.7")

    with pytest.raises(Throttled):
        # A different number from the same pumping host: still blocked.
        issue_otp(phone_number="0666123456", purpose="register", ip="196.1.55.7")

    # A different IP is unaffected — the cap is per source.
    issue_otp(phone_number="0666123456", purpose="register", ip="41.100.9.9")


def test_sms_failure_leaves_no_row_and_spends_no_budget():
    with override_settings(SMS_BACKEND="tests.helpers.FailingSmsBackend"):
        with pytest.raises(SmsError):
            issue_otp(phone_number=PHONE, purpose="register")

    # Nobody received the code, so nothing may be waiting to be entered...
    assert not PhoneOtp.objects.exists()
    # ...and the failed attempt did not burn the cooldown/daily budget of the
    # legitimate user who retries with a healthy provider right after.
    row = issue_otp(phone_number=PHONE, purpose="register")
    assert row.pk is not None


# ---------------------------------------------------------------------------
# Request endpoint (``POST /api/auth/phone/otp/``)
# ---------------------------------------------------------------------------
def test_register_purpose_sends_the_first_code(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json"
    )

    assert response.status_code == 200
    assert outbox[-1]["phone_number"] == E164


def test_register_purpose_refuses_an_already_registered_number(api_client):
    PhoneOnlyUserFactory(phone_number=E164)

    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json"
    )

    assert response.status_code == 400
    # Envelope: the honest "number is taken" rejection keeps the field message
    # in ``details`` and gains a code the client can branch on.
    assert response.data["code"] == "phone_already_registered"
    assert "phone_number" in response.data["details"]
    assert outbox == []  # nothing sent, no money spent


def test_login_purpose_never_confirms_an_unknown_number(api_client):
    """Enumeration defence: an attacker probing a harvested list gets the same
    200 as everyone else — and the platform pays for no SMS."""
    response = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")

    assert response.status_code == 200
    assert outbox == []


def test_login_purpose_sends_for_a_verified_binding(api_client):
    PhoneOnlyUserFactory(phone_number=E164)

    response = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")

    assert response.status_code == 200
    assert outbox[-1]["phone_number"] == E164


def test_password_reset_purpose_sends_for_an_existing_number(api_client):
    PhoneOnlyUserFactory(phone_number=E164)

    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "password_reset"}, format="json"
    )

    assert response.status_code == 200
    assert outbox[-1]["phone_number"] == E164


def test_anonymous_cannot_request_the_phone_change_purpose(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "phone_change"}, format="json"
    )

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"
    assert outbox == []


def test_malformed_number_is_rejected(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": "not-a-phone", "purpose": "register"}, format="json"
    )

    assert response.status_code == 400
    assert "phone_number" in response.data["details"]
    assert outbox == []


def test_resend_cooldown_returns_429(api_client):
    first = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json")
    second = api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json")

    assert first.status_code == 200
    assert second.status_code == 429
    assert len([m for m in outbox if m["phone_number"] == E164]) == 1


@override_settings(OTP_MAX_PER_IP_PER_DAY=1, OTP_RESEND_COOLDOWN_SECONDS=0)
def test_daily_ip_budget_returns_429(api_client):
    codes = []
    for _ in range(3):
        codes.append(
            api_client.post(
                OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json"
            ).status_code
        )

    assert codes[0] == 200
    assert codes[1:] == [429, 429]
    assert len([m for m in outbox if m["phone_number"] == E164]) == 1


@override_settings(SMS_BACKEND="tests.helpers.FailingSmsBackend")
def test_provider_outage_answers_503(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json"
    )

    assert response.status_code == 503
    assert response.data["code"] == "sms_delivery_unavailable"
    assert not PhoneOtp.objects.exists()


def test_invalid_number_never_reaches_the_provider(api_client):
    response = api_client.post(
        OTP_URL, {"phone_number": "12345", "purpose": "register"}, format="json"
    )

    assert response.status_code == 400
    assert outbox == []


def test_code_sent_to_the_number_actually_entered(api_client):
    """The normalized E.164 target and the stored row agree — one number,
    one value (docs/todo.md §0.3 #7)."""
    api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "register"}, format="json")

    row = PhoneOtp.objects.get()
    assert row.phone_number == E164
    assert re.fullmatch(r"[0-9]{6}", last_sms_code())
    # The stored row only ever holds a hash of the code — a database dump
    # must not hand over live credentials.
    field_names = {field.name for field in PhoneOtp._meta.get_fields()}
    assert "code" not in field_names
    assert row.code_hash != last_sms_code()


def test_verify_endpoint_roundtrip(api_client):
    """The full request→code→login pair the SPA drives (used by the
    end-to-end identity tests too)."""
    user = PhoneOnlyUserFactory(phone_number=E164)
    api_client.post(OTP_URL, {"phone_number": PHONE, "purpose": "login"}, format="json")

    from tests.helpers import last_sms_code as extract

    response = api_client.post(
        "/api/v1/auth/phone/login/",
        {"phone_number": PHONE, "code": extract()},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["user"]["phone_number"] == E164
    assert User.objects.get(pk=user.pk).last_login is not None
