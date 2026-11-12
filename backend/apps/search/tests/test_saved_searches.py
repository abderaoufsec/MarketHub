"""Saved searches, alerts and analytics commands (Phase 15).

The alert tests are end-to-end through the signal: create a saved search, then
create a listing, then read the real ``mail.outbox`` / SMS / WhatsApp outboxes.
That is the only way to prove "instant" means *published*, not "saved and
forgotten".
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.products.models import Product
from apps.search.models import SavedSearch, SearchQuery
from apps.search.notifications import whatsapp_outbox
from apps.users.sms import outbox as sms_outbox
from tests.factories import ProductFactory, SellerFactory, UserFactory

pytestmark = pytest.mark.django_db

SAVED_URL = "/api/v1/search/saved/"


def saved_payload(**overrides):
    payload = {
        "name": "iPhone watch",
        "params": {"q": "iphone", "min_price": "1000"},
        "frequency": SavedSearch.Frequency.INSTANT,
        "notify_email": True,
    }
    payload.update(overrides)
    return payload


def make_phone_buyer(**overrides):
    buyer = UserFactory(**overrides)
    buyer.phone_number = "+213555000111"
    buyer.save(update_fields=["phone_number"])
    return buyer


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_canonicalizes_params_and_ignores_pagination(buyer, api_client):
    api_client.force_authenticate(user=buyer)
    response = api_client.post(
        SAVED_URL,
        saved_payload(
            params={"q": " iPhone ", "min_price": "1000", "cursor": "abc", "nonsense": "x"}
        ),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["params"] == {"q": "iPhone", "min_price": "1000"}
    assert "q=iPhone" in response.data["query_string"]
    assert "cursor" not in response.data["query_string"]


def test_saved_searches_are_private(buyer, api_client):
    mine = SavedSearch.objects.create(user=buyer, params={"q": "mine"})
    other = SavedSearch.objects.create(user=UserFactory(), params={"q": "other"})
    api_client.force_authenticate(user=buyer)

    listed = api_client.get(SAVED_URL)
    assert [row["id"] for row in listed.data] == [mine.pk]

    assert api_client.get(f"{SAVED_URL}{other.pk}/").status_code == 404
    assert api_client.delete(f"{SAVED_URL}{other.pk}/").status_code == 404


def test_channels_need_an_address_and_at_least_one_channel(buyer, api_client):
    api_client.force_authenticate(user=buyer)

    none = api_client.post(
        SAVED_URL,
        saved_payload(notify_email=False, notify_sms=False, notify_whatsapp=False),
        format="json",
    )
    assert none.status_code == 400

    sms = api_client.post(SAVED_URL, saved_payload(notify_sms=True), format="json")
    assert sms.status_code == 400
    assert "notify_sms" in sms.data["details"]

    no_email = UserFactory(email=None)
    email_client = APIClient()
    email_client.force_authenticate(user=no_email)
    email = email_client.post(SAVED_URL, saved_payload(), format="json")
    assert email.status_code == 400
    assert "notify_email" in email.data["details"]


def test_update_toggles_channels_and_validates_the_combined_state(buyer, api_client):
    buyer.phone_number = "+213555000111"
    buyer.save(update_fields=["phone_number"])
    saved = SavedSearch.objects.create(user=buyer, params={"q": "iphone"})
    api_client.force_authenticate(user=buyer)

    updated = api_client.patch(
        f"{SAVED_URL}{saved.pk}/",
        {"notify_email": False, "notify_sms": True},
        format="json",
    )

    assert updated.status_code == 200, updated.data
    saved.refresh_from_db()
    assert saved.notify_email is False
    assert saved.notify_sms is True


# ---------------------------------------------------------------------------
# Instant alerts
# ---------------------------------------------------------------------------


@pytest.fixture
def alert_outboxes():
    mail.outbox.clear()
    sms_outbox.clear()
    whatsapp_outbox.clear()
    yield
    mail.outbox.clear()
    sms_outbox.clear()
    whatsapp_outbox.clear()


def test_instant_alert_fires_on_publish_on_email_and_sms(buyer, alert_outboxes):
    buyer.phone_number = "+213555000111"
    buyer.save(update_fields=["phone_number"])
    saved = SavedSearch.objects.create(
        user=buyer,
        name="iPhones",
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
        notify_sms=True,
    )

    listing = ProductFactory(name="iPhone 15 Pro")

    assert len(mail.outbox) == 1
    assert "iPhone 15 Pro" in mail.outbox[0].body
    assert listing.canonical_path in mail.outbox[0].body
    assert len(sms_outbox) == 1
    assert "iPhone 15 Pro" in sms_outbox[0]["message"]
    saved.refresh_from_db()
    assert saved.last_notified_at is not None


def test_instant_alert_does_not_repeat_on_edit(buyer, alert_outboxes):
    saved = SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
    )
    listing = ProductFactory(name="iPhone 15")
    assert len(mail.outbox) == 1
    saved.refresh_from_db()
    assert saved.last_notified_at is not None

    listing.name = "iPhone 15 Pro"
    listing.save()

    assert len(mail.outbox) == 1


def test_seller_never_gets_an_alert_for_their_own_listing(alert_outboxes):
    seller = SellerFactory()
    SavedSearch.objects.create(
        user=seller,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
    )

    ProductFactory(store=None, seller=seller, name="iPhone 15")

    assert mail.outbox == []


def test_non_matching_listing_does_not_alert(buyer, alert_outboxes):
    SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
    )

    ProductFactory(name="Samsung Galaxy")

    assert mail.outbox == []


def test_whatsapp_channel_uses_its_console_outbox(buyer, alert_outboxes):
    buyer.phone_number = "+213555000111"
    buyer.save(update_fields=["phone_number"])
    SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=False,
        notify_whatsapp=True,
    )

    ProductFactory(name="iPhone 15")

    assert len(whatsapp_outbox) == 1
    assert whatsapp_outbox[0]["phone_number"] == "+213555000111"


def test_instant_alerts_can_be_switched_off(buyer, alert_outboxes, settings):
    settings.SEARCH_INSTANT_ALERTS = False
    SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
    )

    ProductFactory(name="iPhone 15")

    assert mail.outbox == []


def test_alert_failure_never_breaks_publish(buyer, alert_outboxes, monkeypatch):
    SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
    )

    def explode(*args, **kwargs):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr("apps.search.alerts.deliver", explode)

    listing = ProductFactory(name="iPhone 15")

    assert listing.pk is not None
    assert mail.outbox == []


def test_one_dead_channel_does_not_block_the_other(buyer, alert_outboxes, monkeypatch):
    buyer.phone_number = "+213555000111"
    buyer.save(update_fields=["phone_number"])
    saved = SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.INSTANT,
        notify_email=True,
        notify_sms=True,
    )

    def explode(*args, **kwargs):
        raise RuntimeError("sms gateway down")

    monkeypatch.setattr("apps.search.notifications.send_sms", explode)
    ProductFactory(name="iPhone 15")

    assert len(mail.outbox) == 1
    saved.refresh_from_db()
    # The alert counts as failed, so it will be retried by the next digest.
    assert saved.last_notified_at is None


# ---------------------------------------------------------------------------
# Daily digest
# ---------------------------------------------------------------------------


def test_daily_digest_sends_once_and_updates_the_timestamp(buyer, alert_outboxes):
    saved = SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.DAILY,
        notify_email=True,
    )
    ProductFactory(name="iPhone 15")
    # Instant alerts ignore DAILY searches.
    assert mail.outbox == []

    call_command("send_search_alerts")
    assert len(mail.outbox) == 1
    saved.refresh_from_db()
    first_sent = saved.last_notified_at
    assert first_sent is not None

    call_command("send_search_alerts")
    assert len(mail.outbox) == 1


def test_daily_digest_dry_run_does_not_send_or_touch_state(buyer, alert_outboxes):
    saved = SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.DAILY,
        notify_email=True,
    )
    ProductFactory(name="iPhone 15")
    SavedSearch.objects.filter(pk=saved.pk).update(
        last_notified_at=timezone.now() - timedelta(days=2)
    )

    call_command("send_search_alerts", "--dry-run")

    assert mail.outbox == []
    saved.refresh_from_db()
    assert saved.last_notified_at < timezone.now() - timedelta(days=1)


def test_daily_digest_reports_a_delivery_failure(buyer, alert_outboxes, monkeypatch, capsys):
    SavedSearch.objects.create(
        user=buyer,
        params={"q": "iphone"},
        frequency=SavedSearch.Frequency.DAILY,
        notify_email=True,
    )
    ProductFactory(name="iPhone 15")

    def explode(*args, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("apps.search.alerts.deliver", explode)
    call_command("send_search_alerts")

    assert "1 failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Analytics + maintenance commands
# ---------------------------------------------------------------------------


def test_rebuild_search_index_repairs_a_stale_document(db):
    product = ProductFactory(name="Galaxy S24")
    Product.objects.filter(pk=product.pk).update(search_document="")

    call_command("rebuild_search_index")

    product.refresh_from_db()
    assert "galaxy" in product.search_document
    assert "s24" in product.search_document


def test_search_report_prints_top_and_zero_result_queries(db, capsys):
    SearchQuery.objects.create(query="galaxy", normalized="galaxy", result_count=3)
    SearchQuery.objects.create(query="zzz", normalized="zzz", result_count=0, zero_results=True)

    call_command("search_report", "--days", "7")

    output = capsys.readouterr().out
    assert "Top queries" in output
    assert "galaxy" in output
    assert "Zero-result" in output
    assert "zzz" in output

    call_command("search_report", "--json")
    assert '"top_queries"' in capsys.readouterr().out
