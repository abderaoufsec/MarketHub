"""Search API behaviour (Phase 15).

The tests are grouped by the bullet they pin:

* bilingual matching (Arabic normalization, French accents, transliteration,
  Darija synonyms, typos);
* facets (own filter removed, across-facet narrowing);
* orderings (relevance/newest/price/distance) and cursor pagination;
* zero-result recovery and analytics;
* suggestions/recent searches.

Every assertion goes through the public HTTP API where the bullet is about
behaviour; normalization internals have their own pure-function file.
"""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import AttributeDefinition
from apps.products.models import Product
from apps.search.models import SearchQuery
from apps.search.suggestions import did_you_mean
from tests.factories import (
    AttributeDefinitionFactory,
    CategoryFactory,
    InventoryFactory,
    ProductFactory,
    ProductImageFactory,
    SellerFactory,
    UserFactory,
    WilayaFactory,
)

pytestmark = pytest.mark.django_db

SEARCH_URL = "/api/v1/search/"
SUGGESTIONS_URL = "/api/v1/search/suggestions/"
PRODUCTS_URL = "/api/v1/products/"
PRODUCT_SEARCH_URL = "/api/v1/products/search/"


def names(response):
    return {row["name"] for row in response.data["results"]}


def next_path(response):
    url = response.data["next"]
    assert url
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.path}?{parsed.query}"


# ---------------------------------------------------------------------------
# Bilingual text matching
# ---------------------------------------------------------------------------


def test_search_strips_the_arabic_article(api_client):
    phone = ProductFactory(name="هاتف سامسونج جالاكسي")
    ProductFactory(name="ثلاجة كوندور")

    response = api_client.get(SEARCH_URL, {"q": "الهاتف"})

    assert response.status_code == 200
    assert names(response) == {phone.name}


def test_arabic_query_finds_a_french_listing_through_synonyms(api_client):
    car = ProductFactory(name="Voiture Renault Clio", description="Essence, 2019")
    ProductFactory(name="Réfrigérateur Samsung", description="Noiseless")

    response = api_client.get(SEARCH_URL, {"q": "سيارة"})

    assert names(response) == {car.name}


def test_french_query_finds_an_arabic_listing(api_client):
    car = ProductFactory(name="سيارة رينو كليو")
    ProductFactory(name="ثلاجة كوندور")

    response = api_client.get(SEARCH_URL, {"q": "voiture"})

    assert names(response) == {car.name}


def test_latin_transliteration_matches_an_arabic_listing(api_client):
    phone = ProductFactory(name="هاتف سامسونج")
    ProductFactory(name="ثلاجة كوندور")

    # The document carries the Latin transliteration of Arabic tokens, so a
    # Latin keyboard finds the listing without knowing the Arabic spelling.
    response = api_client.get(SEARCH_URL, {"q": "samswnj"})

    assert names(response) == {phone.name}
    assert "samswnj" in phone.search_document


def test_typo_fallback_finds_the_brand_and_is_flagged(api_client):
    phone = ProductFactory(name="Samsung Galaxy S24")
    ProductFactory(name="Condor Plume P8")

    response = api_client.get(SEARCH_URL, {"q": "samsug"})

    assert names(response) == {phone.name}
    assert response.data["meta"]["used_fuzzy"] is True


def test_accents_are_optional_in_french(api_client):
    fridge = ProductFactory(name="Réfrigérateur Samsung")

    response = api_client.get(SEARCH_URL, {"q": "refrigerateur"})

    assert names(response) == {fridge.name}


def test_stopword_only_query_is_a_no_op(api_client):
    ProductFactory(name="One")
    ProductFactory(name="Two")

    response = api_client.get(SEARCH_URL, {"q": "de la"})

    assert response.status_code == 200
    assert len(response.data["results"]) == 2


def test_unmatched_nonsense_query_is_not_the_whole_catalogue(api_client):
    """Postgres ranks an empty (all-stopword) tsquery at 1e-20, not zero.

    Treating any positive rank as a match made nonsense queries return every
    listing - the opposite of "no results" recovery.
    """
    ProductFactory(name="One")
    ProductFactory(name="Two")

    response = api_client.get(SEARCH_URL, {"q": "zzzz-no-such-listing-zzzz"})

    assert response.status_code == 200
    assert response.data["results"] == []
    assert response.data["meta"]["total"] == 0


def test_search_document_indexes_category_location_and_attributes():
    wilaya = WilayaFactory(name_fr="Blida", name_ar="البليدة")
    category = CategoryFactory(name_fr="Téléphones", name_ar="هواتف")
    product = ProductFactory(
        name="Galaxy",
        category=category,
        wilaya=wilaya,
        attributes_json={"brand": "samsung", "storage": 128},
    )

    document = product.search_document

    assert "telephones" in document
    assert "blida" in document
    assert "samsung" in document
    assert "128" in document


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------


@pytest.fixture
def facet_data(db):
    phones = CategoryFactory(slug="phones", name_fr="Téléphones", name_ar="هواتف")
    vehicles = CategoryFactory(slug="vehicles", name_fr="Véhicules", name_ar="سيارات")
    algiers = WilayaFactory(
        code="16", name_fr="Alger", latitude=Decimal("36.753800"), longitude=Decimal("3.058800")
    )
    oran = WilayaFactory(
        code="31", name_fr="Oran", latitude=Decimal("35.697100"), longitude=Decimal("-0.630800")
    )

    AttributeDefinitionFactory(
        category=phones,
        key="condition",
        label_fr="État",
        type=AttributeDefinition.Type.ENUM,
        filterable=True,
        choices=[
            {"value": "new", "label_fr": "Neuf", "label_ar": "جديد"},
            {"value": "used", "label_fr": "Occasion", "label_ar": "مستعمل"},
        ],
    )
    AttributeDefinitionFactory(
        category=phones,
        key="brand",
        label_fr="Marque",
        type=AttributeDefinition.Type.ENUM,
        filterable=True,
        choices=[{"value": "samsung", "label_fr": "Samsung"}],
    )

    p1 = ProductFactory(
        name="Galaxy S24",
        category=phones,
        wilaya=algiers,
        base_price=Decimal("1000"),
        attributes_json={"condition": "new", "brand": "samsung"},
    )
    p2 = ProductFactory(
        name="Galaxy A15",
        category=phones,
        wilaya=oran,
        base_price=Decimal("5000"),
        attributes_json={"condition": "used", "brand": "samsung"},
    )
    p3 = ProductFactory(
        name="Clio",
        category=vehicles,
        wilaya=algiers,
        base_price=Decimal("20000"),
        attributes_json={},
    )
    ProductImageFactory(product=p1)
    return {
        "phones": phones,
        "vehicles": vehicles,
        "algiers": algiers,
        "oran": oran,
        "p1": p1,
        "p2": p2,
        "p3": p3,
    }


def test_facets_count_every_group_and_keep_the_selection_removable(api_client, facet_data):
    response = api_client.get(SEARCH_URL)
    facets = response.data["facets"]

    assert {row["value"]: row["count"] for row in facets["category"]} == {
        "phones": 2,
        "vehicles": 1,
    }
    assert {row["value"]: row["count"] for row in facets["wilaya"]} == {
        str(facet_data["algiers"].pk): 2,
        str(facet_data["oran"].pk): 1,
    }
    assert {row["value"]: row["count"] for row in facets["condition"]} == {
        "new": 1,
        "used": 1,
    }
    # The localized label comes from the definition, not the raw slug.
    assert {row["value"]: row["label"] for row in facets["condition"]}["new"] == "Neuf"
    assert facets["attributes"]["brand"]["label"] == "Marque"
    assert facets["attributes"]["brand"]["values"] == [
        {"value": "samsung", "label": "Samsung", "count": 2}
    ]
    assert {row["value"]: row["count"] for row in facets["photos"]} == {
        "true": 1,
        "false": 2,
    }
    assert {row["value"]: row["count"] for row in facets["seller_type"]}["store"] == 3

    # Selecting a category removes *its own* filter from the category facet
    # (so the sidebar can switch) but narrows every other facet.
    filtered = api_client.get(SEARCH_URL, {"category": "phones"})
    assert filtered.data["meta"]["total"] == 2
    assert {row["value"] for row in filtered.data["facets"]["category"]} >= {"phones", "vehicles"}
    assert {row["value"]: row["count"] for row in filtered.data["facets"]["wilaya"]} == {
        str(facet_data["algiers"].pk): 1,
        str(facet_data["oran"].pk): 1,
    }

    # Same rule for a condition selection.
    condition = api_client.get(SEARCH_URL, {"condition": "new"})
    assert condition.data["meta"]["total"] == 1
    assert {row["value"]: row["count"] for row in condition.data["facets"]["condition"]} == {
        "new": 1,
        "used": 1,
    }


def test_facets_are_localized(api_client, facet_data):
    response = api_client.get(SEARCH_URL, HTTP_ACCEPT_LANGUAGE="ar")

    labels = [row["label"] for row in response.data["facets"]["category"]]
    assert "هواتف" in labels


def test_price_and_date_facets_use_stable_bucket_keys(api_client, facet_data):
    response = api_client.get(SEARCH_URL)

    assert [row["value"] for row in response.data["facets"]["price"]] == [
        "under_5k",
        "5k_20k",
        "20k_100k",
        "over_100k",
    ]
    assert [row["value"] for row in response.data["facets"]["posted"]] == [
        "today",
        "7d",
        "30d",
        "older",
    ]


# ---------------------------------------------------------------------------
# Filters, sorts, pagination
# ---------------------------------------------------------------------------


def test_in_stock_is_honoured_by_the_catalogue_and_search(api_client):
    stocked = ProductFactory(name="Stocked")
    InventoryFactory(product=stocked, stock_quantity=2)
    ProductFactory(name="Out of stock")
    classified_seller = SellerFactory()
    ProductFactory(name="Classified", store=None, seller=classified_seller)

    listing = api_client.get(PRODUCTS_URL, {"in_stock": "true"})
    assert names(listing) == {"Stocked"}

    search = api_client.get(SEARCH_URL, {"in_stock": "true"})
    assert names(search) == {"Stocked"}


def test_attribute_filter_validates_the_key(api_client, facet_data):
    response = api_client.get(SEARCH_URL, {"attr_unknown": "x"})
    assert response.status_code == 400

    response = api_client.get(SEARCH_URL, {"attr_brand": "samsung"})
    assert response.status_code == 200
    assert response.data["meta"]["total"] == 2


def test_price_sort_and_newest_sort(api_client, facet_data):
    cheap = api_client.get(SEARCH_URL, {"sort": "price_asc"})
    assert [row["name"] for row in cheap.data["results"]] == [
        "Galaxy S24",
        "Galaxy A15",
        "Clio",
    ]

    expensive = api_client.get(SEARCH_URL, {"sort": "price_desc"})
    assert next(row["name"] for row in expensive.data["results"]) == "Clio"

    old = facet_data["p1"]
    Product.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
    newest = api_client.get(SEARCH_URL, {"sort": "newest"})
    assert newest.data["results"][-1]["name"] == "Galaxy S24"


def test_relevance_prefers_the_better_text_match(api_client):
    good = ProductFactory(name="Samsung Galaxy S24", description="Samsung flagship phone")
    ProductFactory(name="Samsung charger", description="A charger")
    ProductFactory(name="Galaxy case", description="A case")

    response = api_client.get(SEARCH_URL, {"q": "samsung galaxy", "sort": "relevance"})

    assert response.data["results"][0]["name"] == good.name
    assert response.data["meta"]["sort"] == "relevance"


def test_distance_sort_uses_wilaya_centroids(api_client, facet_data):
    response = api_client.get(
        SEARCH_URL,
        {"sort": "distance", "lat": "36.7538", "lng": "3.0588"},
    )

    assert response.status_code == 200
    first = response.data["results"][0]
    assert first["name"] == "Clio"  # Algiers; Galaxy S24 is also Algiers
    assert first["distance_km"] < 1
    oran = next(row for row in response.data["results"] if row["name"] == "Galaxy A15")
    assert oran["distance_km"] > 300


def test_distance_requires_coordinates(api_client):
    response = api_client.get(SEARCH_URL, {"sort": "distance"})
    assert response.status_code == 400


def test_invalid_sort_and_coordinates_are_400(api_client):
    assert api_client.get(SEARCH_URL, {"sort": "sideways"}).status_code == 400
    assert api_client.get(SEARCH_URL, {"lat": "x", "lng": "3"}).status_code == 400
    assert api_client.get(SEARCH_URL, {"lat": "36"}).status_code == 400


def test_cursor_pagination_walks_every_match_once(api_client, facet_data):
    first = api_client.get(SEARCH_URL, {"page_size": 2})
    assert first.data["meta"]["total"] == 3
    assert len(first.data["results"]) == 2
    assert first.data["next"]

    second = api_client.get(next_path(first))
    assert second.status_code == 200
    assert len(second.data["results"]) == 1

    seen = {row["id"] for row in first.data["results"]} | {
        row["id"] for row in second.data["results"]
    }
    assert len(seen) == 3


def test_catalogue_search_uses_the_same_matcher(api_client):
    phone = ProductFactory(name="Samsung Galaxy S24")

    response = api_client.get(PRODUCT_SEARCH_URL, {"q": "samsug"})

    assert names(response) == {phone.name}
    assert response.data["meta"]["used_fuzzy"] is True


# ---------------------------------------------------------------------------
# Zero-result recovery, analytics, suggestions
# ---------------------------------------------------------------------------


def test_zero_results_offer_a_correction_and_removable_filters(api_client, facet_data):
    response = api_client.get(SEARCH_URL, {"q": "zzzqqq", "with_photos": "true"})

    assert response.data["meta"]["total"] == 0
    # Dropping the photo filter still leaves the text query dead, so only the
    # *text* relaxation is useful here; it must be listed with a real count.
    params = {row["param"] for row in response.data["meta"]["relaxations"]}
    assert "q" in params


def test_nearby_wilayas_recover_a_location_dead_end(api_client, facet_data):
    # Oran has products but none with a photo; Algiers has the only photo.
    response = api_client.get(SEARCH_URL, {"wilaya": facet_data["oran"].pk, "with_photos": "true"})

    assert response.data["meta"]["total"] == 0
    nearby = response.data["meta"]["nearby_wilayas"]
    assert nearby and nearby[0]["value"] == str(facet_data["algiers"].pk)
    assert nearby[0]["count"] >= 1
    assert nearby[0]["distance_km"] > 0


def test_did_you_mean_uses_the_catalogue_vocabulary(db):
    CategoryFactory(slug="smartphones", name_fr="Smartphones")
    cache.clear()

    assert did_you_mean("smartphnes") == "smartphones"


def test_search_is_recorded_once_per_first_page(api_client):
    for index in range(3):
        ProductFactory(name=f"Galaxy S24 {index}")
    first = api_client.get(SEARCH_URL, {"q": "galaxy", "page_size": 1})
    assert SearchQuery.objects.count() == 1
    row = SearchQuery.objects.get()
    assert row.normalized == "galaxy"
    assert row.zero_results is False

    api_client.get(next_path(first))
    assert SearchQuery.objects.count() == 1


def test_zero_result_search_is_recorded(api_client):
    api_client.get(SEARCH_URL, {"q": "zzzqqq"})
    row = SearchQuery.objects.get()
    assert row.zero_results is True
    assert row.result_count == 0


def test_suggestions_bring_recent_terms_products_and_categories(buyer, api_client):
    category = CategoryFactory(slug="telephones", name_fr="Téléphones")
    ProductFactory(name="Apple iPhone 15", category=category)
    SearchQuery.objects.create(user=buyer, query="iphone 15", normalized="iphone 15")
    client = api_client
    client.force_authenticate(user=buyer)

    response = client.get(SUGGESTIONS_URL, {"q": "iph"})

    assert response.status_code == 200
    assert "iphone 15" in response.data["terms"]
    assert {row["name"] for row in response.data["products"]} == {"Apple iPhone 15"}

    phone = client.get(SUGGESTIONS_URL, {"q": "tele"})
    assert any(row["name"] == "Téléphones" for row in phone.data["categories"])


def test_suggestions_are_empty_below_two_characters(api_client):
    response = api_client.get(SUGGESTIONS_URL, {"q": "a"})
    assert response.data["terms"] == []
    assert response.data["products"] == []


def test_recent_searches_are_private_and_clearable(buyer, api_client):
    api_client.force_authenticate(user=buyer)
    SearchQuery.objects.create(user=buyer, query="galaxy", normalized="galaxy")

    response = api_client.get("/api/v1/search/recent/")
    assert [row["query"] for row in response.data] == ["galaxy"]

    assert api_client.delete("/api/v1/search/recent/").status_code == 204
    assert SearchQuery.objects.filter(user=buyer).count() == 0


def test_recent_searches_require_auth(api_client):
    assert api_client.get("/api/v1/search/recent/").status_code in (401, 403)


def test_saved_search_validation_rejects_unknown_attributes(buyer, api_client):
    api_client.force_authenticate(user=buyer)
    response = api_client.post(
        "/api/v1/search/saved/",
        {"params": {"attr_nope": "x"}},
        format="json",
    )
    assert response.status_code == 400
