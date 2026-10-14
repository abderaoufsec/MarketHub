"""Phase 11: account messages and API labels follow a language.

Two different rules, both deliberate:

* **Emails and SMS** follow the *user's* ``preferred_language`` — they arrive
  out of band, with no ``Accept-Language`` header to negotiate, so the stored
  preference is the only honest signal.
* **API ``*_label`` fields** follow the *request's* ``Accept-Language`` — they
  are rendered inside a request, exactly like the error envelope
  (``core/exceptions.py``).
"""

import pytest
from django.core import mail

from apps.users.models import User
from tests.factories import OrderFactory, UserFactory

pytestmark = pytest.mark.django_db

PROFILE_URL = "/api/v1/auth/profile/"
ORDERS_URL = "/api/v1/orders/"


def test_verification_email_uses_the_default_preference_french():
    from apps.users.email import send_verification_email

    user = UserFactory(is_verified=False)  # preferred_language defaults to "fr"

    assert send_verification_email(user) is True
    assert mail.outbox[0].subject == "Vérifiez votre compte MarketHub"


def test_verification_email_follows_an_arabic_preference():
    from apps.users.email import send_verification_email

    user = UserFactory(is_verified=False, preferred_language="ar")

    assert send_verification_email(user) is True
    assert mail.outbox[0].subject == "تحقق من حسابك على MarketHub"
    assert "{link}" not in mail.outbox[0].body  # placeholders were formatted


def test_verification_email_follows_an_english_preference():
    from apps.users.email import send_verification_email

    user = UserFactory(is_verified=False, preferred_language="en")

    assert send_verification_email(user) is True
    assert mail.outbox[0].subject == "Verify your MarketHub account"


def test_profile_update_can_change_the_preferred_language(buyer_client, buyer):
    response = buyer_client.put(PROFILE_URL, {"preferred_language": "ar"}, format="json")

    assert response.status_code == 200
    buyer.refresh_from_db()
    assert buyer.preferred_language == "ar"
    # The PUT body wraps the updated user under "user".
    assert response.data["user"]["preferred_language"] == "ar"


def test_profile_update_rejects_an_unsupported_language(buyer_client):
    response = buyer_client.put(PROFILE_URL, {"preferred_language": "de"}, format="json")

    assert response.status_code == 400
    assert "preferred_language" in response.data["details"]
    assert not User.objects.filter(preferred_language="de").exists()


def test_registration_accepts_a_language_preference(api_client):
    response = api_client.post(
        "/api/v1/auth/register/",
        {
            "first_name": "Amina",
            "last_name": "Bensalem",
            "username": "amina",
            "email": "amina@example.com",
            "password": "Str0ng!Passw0rd",
            "password_confirm": "Str0ng!Passw0rd",
            "preferred_language": "ar",
        },
        format="json",
    )

    assert response.status_code == 201
    assert User.objects.get(email="amina@example.com").preferred_language == "ar"


def test_order_labels_follow_accept_language(buyer_client, buyer):
    OrderFactory(user=buyer, order_status="PENDING", payment_status="SUCCESSFUL")

    french = buyer_client.get(ORDERS_URL, HTTP_ACCEPT_LANGUAGE="fr")
    english = buyer_client.get(ORDERS_URL, HTTP_ACCEPT_LANGUAGE="en")
    arabic = buyer_client.get(ORDERS_URL, HTTP_ACCEPT_LANGUAGE="ar")

    # The raw values never move — code branches on them.
    assert french.data["results"][0]["order_status"] == "PENDING"
    assert french.data["results"][0]["payment_status"] == "SUCCESSFUL"

    assert french.data["results"][0]["order_status_label"] == "En attente"
    assert english.data["results"][0]["order_status_label"] == "Pending"
    assert arabic.data["results"][0]["order_status_label"] == "قيد الانتظار"
    assert french.data["results"][0]["payment_status_label"] == "Réussi"
