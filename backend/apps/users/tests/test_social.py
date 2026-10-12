"""Social login (Google / Facebook) — Phase 8 "optional social login".

The provider's answer is mocked at ``social._get_json`` (the transport
boundary): audience/issuer/verified checks and the link-or-create logic are
all under test, while no test ever touches the network.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

SOCIAL_URL = "/api/auth/social/"

GOOGLE_CLAIMS = {
    "sub": "google-uid-1",
    "aud": "test-google-client-id",
    "iss": "https://accounts.google.com",
    "email": "Social.User@Example.com",
    "email_verified": "true",
    "given_name": "Soci",
    "family_name": "Al",
}

FACEBOOK_DEBUG = {"data": {"is_valid": True, "app_id": "fb-app-1"}}
FACEBOOK_ME = {
    "id": "fb-uid-9",
    "email": "fb.user@example.com",
    "first_name": "Face",
    "last_name": "Book",
}


def _patch(payload):
    return patch("apps.users.social._get_json", return_value=payload)


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id")
def test_google_signin_creates_a_verified_account(api_client):
    with _patch(GOOGLE_CLAIMS):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "a-google-id-token"},
            format="json",
        )

    assert response.status_code == 200
    assert response.cookies["access_token"]["httponly"]
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.get(email="social.user@example.com")
    assert user.is_verified is True  # the provider vouched for the address
    assert user.username  # auto-derived
    assert user.first_name == "Soci"
    # A social account must not be able to answer a password prompt.
    assert not user.has_usable_password()


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id")
def test_google_signin_logs_into_an_existing_email_account(api_client):
    existing = UserFactory(email="social.user@example.com")

    with _patch(GOOGLE_CLAIMS):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "a-google-id-token"},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["user"]["id"] == existing.id
    from django.contrib.auth import get_user_model

    assert get_user_model().objects.filter(email="social.user@example.com").count() == 1


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id")
def test_google_signin_refuses_a_token_for_another_application(api_client):
    claims = {**GOOGLE_CLAIMS, "aud": "someone-elses-client"}

    with _patch(claims):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "stolen"},
            format="json",
        )

    assert response.status_code == 400
    assert "error" in response.data


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id")
def test_google_signin_refuses_an_unverified_provider_email(api_client):
    """A provider that does not vouch for the address must not be able to
    verify anyone — that would be an account-takeover path."""
    claims = {**GOOGLE_CLAIMS, "email_verified": "false"}

    with _patch(claims):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "x"},
            format="json",
        )

    assert response.status_code == 400


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id")
def test_google_signin_refuses_a_foreign_issuer(api_client):
    claims = {**GOOGLE_CLAIMS, "iss": "https://evil.example.com"}

    with _patch(claims):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "x"},
            format="json",
        )

    assert response.status_code == 400


def test_google_signin_is_503_when_not_configured(api_client):
    with _patch(GOOGLE_CLAIMS):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "google", "access_token": "x"},
            format="json",
        )

    assert response.status_code == 503


@override_settings(FACEBOOK_APP_ID="fb-app-1", FACEBOOK_APP_SECRET="fb-secret")
def test_facebook_signin_verifies_and_links(api_client):
    existing = UserFactory(email="fb.user@example.com", is_verified=False)

    with patch(
        "apps.users.social._get_json",
        side_effect=[FACEBOOK_DEBUG, FACEBOOK_ME],
    ):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "facebook", "access_token": "a-fb-token"},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["user"]["id"] == existing.id
    existing.refresh_from_db()
    assert existing.is_verified is True


@override_settings(FACEBOOK_APP_ID="fb-app-1", FACEBOOK_APP_SECRET="fb-secret")
def test_facebook_signin_refuses_a_foreign_app_token(api_client):
    debug = {"data": {"is_valid": True, "app_id": "another-app"}}

    with patch("apps.users.social._get_json", side_effect=[debug, FACEBOOK_ME]):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "facebook", "access_token": "x"},
            format="json",
        )

    assert response.status_code == 400


@override_settings(FACEBOOK_APP_ID="fb-app-1", FACEBOOK_APP_SECRET="fb-secret")
def test_facebook_account_without_email_is_refused(api_client):
    """Facebook profiles can hide the address; without one there is no key to
    link, and the user is pointed at phone sign-up instead."""
    me = {k: v for k, v in FACEBOOK_ME.items() if k != "email"}

    with patch("apps.users.social._get_json", side_effect=[FACEBOOK_DEBUG, me]):
        response = api_client.post(
            SOCIAL_URL,
            {"provider": "facebook", "access_token": "x"},
            format="json",
        )

    assert response.status_code == 400


def test_facebook_signin_is_503_when_not_configured(api_client):
    response = api_client.post(
        SOCIAL_URL, {"provider": "facebook", "access_token": "x"}, format="json"
    )

    assert response.status_code == 503


def test_unsupported_provider_is_rejected(api_client):
    response = api_client.post(
        SOCIAL_URL, {"provider": "twitter", "access_token": "x"}, format="json"
    )

    assert response.status_code == 400
    assert "provider" in response.data


def test_provider_outage_answers_502(api_client):
    from apps.users.social import SocialError

    with (
        patch(
            "apps.users.social._get_json",
            side_effect=SocialError("Could not reach the social provider.", status=502),
        ),
        override_settings(GOOGLE_CLIENT_ID="test-google-client-id"),
    ):
        response = api_client.post(
            SOCIAL_URL, {"provider": "google", "access_token": "x"}, format="json"
        )

    assert response.status_code == 502
    assert "error" in response.data


def test_disabled_account_cannot_sign_in_socially(api_client):
    UserFactory(email="banned@example.com", is_active=False)
    claims = {**GOOGLE_CLAIMS, "email": "banned@example.com"}

    with _patch(claims), override_settings(GOOGLE_CLIENT_ID="test-google-client-id"):
        response = api_client.post(
            SOCIAL_URL, {"provider": "google", "access_token": "x"}, format="json"
        )

    assert response.status_code == 403


def test_social_login_is_audited(api_client):
    from apps.users.models import AuthEvent

    with _patch(GOOGLE_CLAIMS), override_settings(GOOGLE_CLIENT_ID="test-google-client-id"):
        api_client.post(SOCIAL_URL, {"provider": "google", "access_token": "x"}, format="json")

    event = AuthEvent.objects.get(event=AuthEvent.LOGIN_SUCCESS, email="social.user@example.com")
    assert event.details["method"] == "google"
    assert event.details["created"] is True
