"""Address CRUD — every object-level permission is checked (IDOR guard)."""
import pytest

from apps.users.models import Address
from tests.factories import AddressFactory, UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = '/api/auth/addresses/'


def address_payload(**overrides):
    data = {
        'address_line1': "10 Avenue de l'Indépendance",
        'city': 'Blida',
        'state_province': 'Blida',
        'postal_code': '09000',
        'country': 'DZ',
        'is_default': True,
    }
    data.update(overrides)
    return data


def test_create_address(buyer_client, buyer):
    response = buyer_client.post(LIST_URL, address_payload(), format='json')

    assert response.status_code == 201
    assert buyer.addresses.count() == 1


def test_list_addresses_only_shows_own(buyer_client, buyer, address):
    other = UserFactory()
    AddressFactory(user=other)

    response = buyer_client.get(LIST_URL)

    assert response.status_code == 200
    ids = [item['id'] for item in response.data['results']]
    assert ids == [address.id]


def test_update_own_address(buyer_client, address):
    response = buyer_client.put(
        f'{LIST_URL}{address.id}/', address_payload(city='Boumerdès'), format='json'
    )

    assert response.status_code == 200
    address.refresh_from_db()
    assert address.city == 'Boumerdès'


def test_delete_own_address(buyer_client, address):
    response = buyer_client.delete(f'{LIST_URL}{address.id}/')

    assert response.status_code == 204
    assert not Address.objects.filter(pk=address.pk).exists()


def test_cannot_touch_other_users_address(buyer_client):
    other = UserFactory()
    foreign = AddressFactory(user=other)

    assert buyer_client.get(f'{LIST_URL}{foreign.id}/').status_code == 404
    assert buyer_client.put(
        f'{LIST_URL}{foreign.id}/', address_payload(city='Hacked'), format='json'
    ).status_code == 404
    assert buyer_client.delete(f'{LIST_URL}{foreign.id}/').status_code == 404
