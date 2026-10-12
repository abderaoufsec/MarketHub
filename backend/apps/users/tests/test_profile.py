"""Profile updates and password changes — including the privilege-escalation
defect recorded in docs/todo.md §0.3 #2/#7 (Phase 6/8 fix them)."""

import pytest
from django.utils import timezone

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PROFILE_URL = "/api/auth/profile/"
CHANGE_PASSWORD_URL = "/api/auth/change-password/"


def test_profile_requires_authentication(api_client):
    response = api_client.get(PROFILE_URL)

    assert response.status_code == 401


def test_profile_returns_own_data(buyer_client, buyer):
    response = buyer_client.get(PROFILE_URL)

    assert response.status_code == 200
    assert response.data["email"] == buyer.email


def test_profile_update_persists_names(buyer_client, buyer):
    response = buyer_client.put(
        PROFILE_URL, {"first_name": "Updated", "last_name": "Name"}, format="json"
    )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.first_name == "Updated"
    assert buyer.last_name == "Name"


def test_profile_update_ignores_read_only_is_verified(buyer_client):
    user = UserFactory(is_verified=False)
    buyer_client.force_authenticate(user=user)

    response = buyer_client.put(PROFILE_URL, {"is_verified": True}, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_verified is False


def test_profile_update_cannot_escalate_to_seller(buyer_client, buyer):
    """Phase 7 fix: ``is_seller`` is read-only on the profile serializer."""
    assert buyer.is_seller is False

    response = buyer_client.put(PROFILE_URL, {"is_seller": True}, format="json")

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.is_seller is False


def test_profile_update_rejects_invalid_phone_number(buyer_client):
    """Phase 8 fix: ``phone_number`` is E.164-validated (§0.3 #7), so junk can
    no longer land in the identity column."""
    response = buyer_client.put(PROFILE_URL, {"phone_number": "not-a-phone"}, format="json")

    assert response.status_code == 400
    assert "phone_number" in response.data


def test_profile_update_normalizes_phone_number(buyer_client, buyer):
    """The Algerian formats people actually type all land as one value."""
    for typed in ("0555 12 34 56", "555123456", "00213555123456", "+213 555 12 34 56"):
        response = buyer_client.put(PROFILE_URL, {"phone_number": typed}, format="json")
        assert response.status_code == 200, typed
        buyer.refresh_from_db()
        assert buyer.phone_number == "+213555123456", typed


def test_profile_update_cannot_take_another_accounts_verified_phone(buyer_client):
    """The partial unique constraint is mirrored as a 400, not an IntegrityError."""
    from tests.factories import PhoneOnlyUserFactory

    holder = PhoneOnlyUserFactory(phone_number="+213555000111")

    response = buyer_client.put(PROFILE_URL, {"phone_number": holder.phone_number}, format="json")

    assert response.status_code == 400
    assert "phone_number" in response.data


def test_changing_the_number_invalidates_the_old_proof(buyer_client, buyer):
    """A new number is stored *unverified* until its own OTP confirms it —
    otherwise binding an unproved number would grant a verified identity."""
    buyer.phone_number = "+213555123456"
    buyer.phone_verified_at = timezone.now()
    buyer.save()

    response = buyer_client.put(PROFILE_URL, {"phone_number": "0777 88 99 00"}, format="json")

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.phone_number == "+213777889900"
    assert buyer.phone_verified is False


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------
def test_change_password_success(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            "old_password": "Str0ng!Passw0rd",
            "new_password": "EvenBetter!Pass9",
            "new_password_confirm": "EvenBetter!Pass9",
        },
        format="json",
    )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.check_password("EvenBetter!Pass9")


def test_change_password_rejects_wrong_old_password(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            "old_password": "TotallyWrong!1",
            "new_password": "EvenBetter!Pass9",
            "new_password_confirm": "EvenBetter!Pass9",
        },
        format="json",
    )

    assert response.status_code == 400
    buyer.refresh_from_db()
    assert buyer.check_password("Str0ng!Passw0rd")


def test_change_password_rejects_mismatch(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            "old_password": "Str0ng!Passw0rd",
            "new_password": "EvenBetter!Pass9",
            "new_password_confirm": "Different!Pass9",
        },
        format="json",
    )

    assert response.status_code == 400


def test_change_password_revokes_other_sessions(buyer_client, buyer):
    """Phase 7: every outstanding refresh token is blacklisted on a password
    change, so a stolen session dies with it."""
    from rest_framework_simplejwt.tokens import RefreshToken

    old_refresh = RefreshToken.for_user(buyer)

    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            "old_password": "Str0ng!Passw0rd",
            "new_password": "EvenBetter!Pass9",
            "new_password_confirm": "EvenBetter!Pass9",
        },
        format="json",
    )

    assert response.status_code == 200
    # The old session cannot be refreshed any more...
    from rest_framework.test import APIClient

    replay = APIClient().post(
        "/api/auth/token/refresh/", {"refresh": str(old_refresh)}, format="json"
    )
    assert replay.status_code == 401
    # ...and this device received a fresh cookie pair to stay logged in.
    assert response.cookies["access_token"]["httponly"]
