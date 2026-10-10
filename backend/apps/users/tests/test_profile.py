"""Profile updates and password changes — including the privilege-escalation
defect recorded in docs/todo.md §0.3 #2/#7 (Phase 6/8 fix them)."""
import pytest

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PROFILE_URL = '/api/auth/profile/'
CHANGE_PASSWORD_URL = '/api/auth/change-password/'


def test_profile_requires_authentication(api_client):
    response = api_client.get(PROFILE_URL)

    assert response.status_code == 401


def test_profile_returns_own_data(buyer_client, buyer):
    response = buyer_client.get(PROFILE_URL)

    assert response.status_code == 200
    assert response.data['email'] == buyer.email


def test_profile_update_persists_names(buyer_client, buyer):
    response = buyer_client.put(
        PROFILE_URL, {'first_name': 'Updated', 'last_name': 'Name'}, format='json'
    )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.first_name == 'Updated'
    assert buyer.last_name == 'Name'


def test_profile_update_ignores_read_only_is_verified(buyer_client):
    user = UserFactory(is_verified=False)
    buyer_client.force_authenticate(user=user)

    response = buyer_client.put(PROFILE_URL, {'is_verified': True}, format='json')

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_verified is False


@pytest.mark.xfail(
    reason="Privilege escalation: UserSerializer exposes is_seller as writable "
    "(docs/todo.md §0.3 #2, fixed in Phase 7)",
    strict=True,
)
def test_profile_update_cannot_escalate_to_seller(buyer_client, buyer):
    assert buyer.is_seller is False

    response = buyer_client.put(PROFILE_URL, {'is_seller': True}, format='json')

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.is_seller is False


@pytest.mark.xfail(
    reason="phone_number is an unvalidated free-text field (docs/todo.md §0.3 #7, "
    "fixed in Phase 8 with E.164 normalization)",
    strict=True,
)
def test_profile_update_rejects_invalid_phone_number(buyer_client):
    response = buyer_client.put(
        PROFILE_URL, {'phone_number': 'not-a-phone'}, format='json'
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------
def test_change_password_success(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            'old_password': 'Str0ng!Passw0rd',
            'new_password': 'EvenBetter!Pass9',
            'new_password_confirm': 'EvenBetter!Pass9',
        },
        format='json',
    )

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.check_password('EvenBetter!Pass9')


def test_change_password_rejects_wrong_old_password(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            'old_password': 'TotallyWrong!1',
            'new_password': 'EvenBetter!Pass9',
            'new_password_confirm': 'EvenBetter!Pass9',
        },
        format='json',
    )

    assert response.status_code == 400
    buyer.refresh_from_db()
    assert buyer.check_password('Str0ng!Passw0rd')


def test_change_password_rejects_mismatch(buyer_client, buyer):
    response = buyer_client.post(
        CHANGE_PASSWORD_URL,
        {
            'old_password': 'Str0ng!Passw0rd',
            'new_password': 'EvenBetter!Pass9',
            'new_password_confirm': 'Different!Pass9',
        },
        format='json',
    )

    assert response.status_code == 400
