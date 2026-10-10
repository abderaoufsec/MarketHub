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

REGISTER_URL = '/api/auth/register/'
LOGIN_URL = '/api/auth/login/'
LOGOUT_URL = '/api/auth/logout/'
REFRESH_URL = '/api/auth/token/refresh/'

VALID_PASSWORD = 'S3cure!Passw0rd'


def registration_payload(**overrides):
    data = {
        'email': 'newbie@example.com',
        'username': 'newbie',
        'password': VALID_PASSWORD,
        'password_confirm': VALID_PASSWORD,
        'first_name': 'New',
        'last_name': 'User',
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_creates_unverified_user(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(), format='json')

    assert response.status_code == 201
    assert response.data['user']['email'] == 'newbie@example.com'
    user = User.objects.get(email='newbie@example.com')
    assert user.is_verified is False
    assert user.check_password(VALID_PASSWORD)


def test_register_rejects_mismatched_passwords(api_client):
    response = api_client.post(
        REGISTER_URL,
        registration_payload(password_confirm='Different!Pass1'),
        format='json',
    )

    assert response.status_code == 400
    assert not User.objects.filter(email='newbie@example.com').exists()


def test_register_rejects_duplicate_email(api_client):
    UserFactory(email='taken@example.com')

    response = api_client.post(
        REGISTER_URL, registration_payload(email='taken@example.com'), format='json'
    )

    assert response.status_code == 400
    assert 'email' in response.data


def test_register_rejects_weak_password(api_client):
    response = api_client.post(
        REGISTER_URL, registration_payload(password='123', password_confirm='123'),
        format='json',
    )

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.xfail(
    reason="Duplicate verification flow: users/views.py AND users/signals.py both "
    "send a link on registration (Phase 8 removes one of them)",
    strict=True,
)
def test_registration_sends_exactly_one_verification_email(api_client):
    before = len(mail.outbox)

    response = api_client.post(REGISTER_URL, registration_payload(), format='json')

    assert response.status_code == 201
    assert len(mail.outbox) - before == 1


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
def test_login_returns_tokens_for_verified_user(api_client):
    user = UserFactory(email='login@example.com')

    response = api_client.post(
        LOGIN_URL, {'email': 'login@example.com', 'password': 'Str0ng!Passw0rd'},
        format='json',
    )

    assert response.status_code == 200
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['user']['email'] == user.email


def test_login_rejected_for_unverified_user(api_client):
    UserFactory(email='pending@example.com', is_verified=False)

    response = api_client.post(
        LOGIN_URL, {'email': 'pending@example.com', 'password': 'Str0ng!Passw0rd'},
        format='json',
    )

    assert response.status_code == 403


def test_login_rejects_wrong_password(api_client):
    UserFactory(email='login@example.com')

    response = api_client.post(
        LOGIN_URL, {'email': 'login@example.com', 'password': 'WrongPass!1'},
        format='json',
    )

    assert response.status_code == 401


def test_login_requires_credentials(api_client):
    response = api_client.post(LOGIN_URL, {'email': 'someone@example.com'}, format='json')

    assert response.status_code == 400


def test_logout_blacklists_refresh_token(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    user = UserFactory()
    api_client.force_authenticate(user=user)
    refresh = RefreshToken.for_user(user)

    response = api_client.post(LOGOUT_URL, {'refresh_token': str(refresh)}, format='json')
    assert response.status_code == 200

    replay = api_client.post(REFRESH_URL, {'refresh': str(refresh)}, format='json')
    assert replay.status_code == 401


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------
def _verification_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f'/api/auth/verify-email/{uid}/{token}/'


def test_verify_email_marks_user_verified(api_client):
    user = UserFactory(is_verified=False)

    response = api_client.get(_verification_url(user))

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_verified is True


def test_verify_email_rejects_invalid_token(api_client):
    user = UserFactory(is_verified=False)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    response = api_client.get(f'/api/auth/verify-email/{uid}/not-a-real-token/')

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_verified is False


def test_verify_email_rejects_unknown_uid(api_client):
    uid = urlsafe_base64_encode(force_bytes(999999))

    response = api_client.get(f'/api/auth/verify-email/{uid}/whatever/')

    assert response.status_code == 400
