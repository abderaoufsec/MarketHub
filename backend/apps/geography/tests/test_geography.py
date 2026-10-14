"""Geography API: the public wilaya/commune endpoints behind the picker."""

import pytest
from django.utils.translation import override

from apps.geography.models import Commune, Wilaya
from tests.factories import CommuneFactory, WilayaFactory

pytestmark = pytest.mark.django_db

WILAYAS_URL = "/api/v1/geography/wilayas/"


def test_wilaya_list_is_public_and_ordered_by_code(client):
    WilayaFactory(code="16", name_fr="Alger", name_ar="الجزائر")
    WilayaFactory(code="09", name_fr="Blida", name_ar="البليدة")

    response = client.get(WILAYAS_URL)

    assert response.status_code == 200
    # Plain array: 69-ish rows do not need a pagination envelope.
    assert isinstance(response.data, list)
    assert [row["code"] for row in response.data] == ["09", "16"]


def test_wilaya_payload_carries_raw_names_and_localised_name(client):
    WilayaFactory(code="09", name_fr="Blida", name_ar="البليدة", name_en="")

    response = client.get(WILAYAS_URL, HTTP_ACCEPT_LANGUAGE="ar")

    row = response.data[0]
    assert row["name_fr"] == "Blida"
    assert row["name_ar"] == "البليدة"
    assert row["name"] == "البليدة"  # localised via Accept-Language


def test_wilaya_display_name_falls_back_to_french_for_english():
    wilaya = WilayaFactory(code="09", name_fr="Blida", name_ar="البليدة", name_en="")

    with override("en"):
        assert wilaya.display_name == "Blida"
    with override("ar"):
        assert wilaya.display_name == "البليدة"
    with override("fr"):
        assert wilaya.display_name == "Blida"


def test_communes_belong_to_the_requested_wilaya_only(client):
    blida = WilayaFactory(code="09", name_fr="Blida")
    oran = WilayaFactory(code="31", name_fr="Oran")
    CommuneFactory(wilaya=blida, name_fr="Boufarik", name_ar="بوفاريك")
    CommuneFactory(wilaya=blida, name_fr="Larbaâ", name_ar="الأربعاء")
    CommuneFactory(wilaya=oran, name_ar="وهران", name_fr="Oran")

    response = client.get(f"{WILAYAS_URL}09/communes/")

    assert response.status_code == 200
    assert sorted(row["name_fr"] for row in response.data) == ["Boufarik", "Larbaâ"]
    assert response.data[0]["wilaya"] == "09"


def test_commune_search_matches_french_and_arabic(client):
    blida = WilayaFactory(code="09", name_fr="Blida")
    CommuneFactory(wilaya=blida, name_fr="Boufarik", name_ar="بوفاريك")
    CommuneFactory(wilaya=blida, name_fr="Larbaâ", name_ar="الأربعاء")

    assert [
        row["name_fr"] for row in client.get(f"{WILAYAS_URL}09/communes/?search=bouf").data
    ] == ["Boufarik"]
    assert [
        row["name_fr"] for row in client.get(f"{WILAYAS_URL}09/communes/?search=أربع").data
    ] == ["Larbaâ"]


def test_unknown_wilaya_is_a_404(client):
    assert client.get(f"{WILAYAS_URL}99/communes/").status_code == 404


def test_inactive_rows_are_not_listed(client):
    WilayaFactory(code="09", name_fr="Blida", is_active=True)
    WilayaFactory(code="31", name_fr="Oran", is_active=False)

    assert [row["code"] for row in client.get(WILAYAS_URL).data] == ["09"]


def test_load_geography_command_is_idempotent():
    from django.core.management import call_command

    call_command("load_geography")
    first = (Wilaya.objects.count(), Commune.objects.count())
    call_command("load_geography")
    second = (Wilaya.objects.count(), Commune.objects.count())

    assert first == (69, 1541)
    assert second == first
