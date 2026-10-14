"""Address CRUD — every object-level permission is checked (IDOR guard).

Phase 11: an address is a street line + Wilaya/Commune (docs/todo.md). The
tests below pin the new write contract (``wilaya_id``/``commune_id``), the
nested read payload, and that a commune from a *different* wilaya is refused
rather than silently re-homed.
"""

import pytest

from apps.users.models import Address
from tests.factories import AddressFactory, CommuneFactory, UserFactory, WilayaFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/auth/addresses/"


def address_payload(**overrides):
    wilaya = WilayaFactory()
    commune = CommuneFactory(wilaya=wilaya)
    data = {
        "address_line1": "10 Avenue de l'Indépendance",
        "wilaya_id": wilaya.id,
        "commune_id": commune.id,
        "is_default": True,
    }
    data.update(overrides)
    return data


def test_create_address(buyer_client, buyer):
    response = buyer_client.post(LIST_URL, address_payload(), format="json")

    assert response.status_code == 201
    address = buyer.addresses.get()
    assert address.wilaya is not None
    assert address.commune is not None
    assert address.country == "DZ"  # derived from the wilaya, not typed
    # The read payload nests the geography so a list renders standalone.
    assert response.data["wilaya"]["id"] == address.wilaya.id
    assert response.data["commune"]["id"] == address.commune.id


def test_create_address_requires_a_wilaya(buyer_client):
    payload = address_payload()
    payload.pop("wilaya_id")

    response = buyer_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 400
    assert "wilaya_id" in response.data["details"]


def test_unknown_wilaya_is_rejected(buyer_client):
    response = buyer_client.post(LIST_URL, address_payload(wilaya_id=999999), format="json")

    assert response.status_code == 400
    assert "wilaya_id" in response.data["details"]


def test_commune_must_belong_to_the_address_wilaya(buyer_client):
    foreign_commune = CommuneFactory(wilaya=WilayaFactory())

    response = buyer_client.post(
        LIST_URL, address_payload(commune_id=foreign_commune.id), format="json"
    )

    assert response.status_code == 400
    assert "commune_id" in response.data["details"]


def test_commune_is_optional(buyer_client):
    payload = address_payload()
    payload.pop("commune_id")

    response = buyer_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    assert response.data["commune"] is None


def test_list_addresses_only_shows_own(buyer_client, buyer, address):
    other = UserFactory()
    AddressFactory(user=other)

    response = buyer_client.get(LIST_URL)

    assert response.status_code == 200
    ids = [item["id"] for item in response.data["results"]]
    assert ids == [address.id]


def test_update_own_address(buyer_client, address):
    new_wilaya = WilayaFactory()
    new_commune = CommuneFactory(wilaya=new_wilaya)

    response = buyer_client.put(
        f"{LIST_URL}{address.id}/",
        address_payload(wilaya_id=new_wilaya.id, commune_id=new_commune.id),
        format="json",
    )

    assert response.status_code == 200
    address.refresh_from_db()
    assert address.wilaya_id == new_wilaya.id
    assert address.commune_id == new_commune.id


def test_legacy_address_without_geography_still_renders(buyer_client, buyer):
    """Rows the data migration could not match keep NULLs — the API shows them."""
    legacy = AddressFactory(user=buyer)
    # Force the un-matched state the migration leaves behind.
    Address.objects.filter(pk=legacy.pk).update(wilaya=None, commune=None)

    response = buyer_client.get(f"{LIST_URL}{legacy.id}/")

    assert response.status_code == 200
    assert response.data["wilaya"] is None
    assert response.data["commune"] is None


def test_delete_own_address(buyer_client, address):
    response = buyer_client.delete(f"{LIST_URL}{address.id}/")

    assert response.status_code == 204
    assert not Address.objects.filter(pk=address.pk).exists()


def test_cannot_touch_other_users_address(buyer_client):
    other = UserFactory()
    foreign = AddressFactory(user=other)

    assert buyer_client.get(f"{LIST_URL}{foreign.id}/").status_code == 404
    assert (
        buyer_client.put(f"{LIST_URL}{foreign.id}/", address_payload(), format="json").status_code
        == 404
    )
    assert buyer_client.delete(f"{LIST_URL}{foreign.id}/").status_code == 404
