"""Home feed and view tracking (Phase 15).

The feed is the infinite home page: ``latest`` (optionally local) and
``trending`` (views + wishlists + reviews), both cursor-paginated. These tests
pin ordering, the wilaya filter, the category row and the atomic view counter
that feeds trending.
"""

from __future__ import annotations

import urllib.parse
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.products.models import Product, Wishlist
from tests.factories import (
    CategoryFactory,
    ProductFactory,
    UserFactory,
    WilayaFactory,
)

pytestmark = pytest.mark.django_db

FEED_URL = "/api/v1/products/feed/"
CATEGORIES_URL = "/api/v1/products/feed/categories/"


def names(response):
    return [row["name"] for row in response.data["results"]]


def next_path(response):
    url = response.data["next"]
    assert url
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.path}?{parsed.query}"


def test_latest_feed_is_newest_first_and_marks_the_section(api_client):
    old = ProductFactory(name="Old")
    new = ProductFactory(name="New")
    Product.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))

    response = api_client.get(FEED_URL, {"section": "latest"})

    assert response.status_code == 200
    assert response.data["section"] == "latest"
    assert names(response) == ["New", "Old"]


def test_latest_feed_honours_the_wilaya(api_client):
    algiers = WilayaFactory(code="16", name_fr="Alger")
    oran = WilayaFactory(code="31", name_fr="Oran")
    here = ProductFactory(name="Here", wilaya=algiers)
    ProductFactory(name="There", wilaya=oran)

    response = api_client.get(FEED_URL, {"section": "latest", "wilaya": algiers.pk})

    assert names(response) == [here.name]


def test_latest_feed_is_cursor_paginated(api_client):
    for index in range(3):
        ProductFactory(name=f"Listing {index}")

    first = api_client.get(FEED_URL, {"page_size": 2})
    assert len(first.data["results"]) == 2
    second = api_client.get(next_path(first))
    assert len(second.data["results"]) == 1
    assert {row["id"] for row in first.data["results"]}.isdisjoint(
        {row["id"] for row in second.data["results"]}
    )


def test_trending_ranks_views_above_recency(api_client):
    viewed = ProductFactory(name="Viewed a lot")
    ProductFactory(name="Fresh")
    Product.objects.filter(pk=viewed.pk).update(views_count=100)

    response = api_client.get(FEED_URL, {"section": "trending"})

    assert response.data["section"] == "trending"
    assert names(response)[0] == "Viewed a lot"


def test_trending_weights_wishlists_too(api_client):
    wanted = ProductFactory(name="Wanted")
    ProductFactory(name="Plain")
    user = UserFactory()
    Wishlist.objects.create(user=user, product=wanted)

    response = api_client.get(FEED_URL, {"section": "trending"})

    assert names(response)[0] == "Wanted"


def test_feed_section_is_validated(api_client):
    response = api_client.get(FEED_URL, {"section": "sideways"})
    assert response.status_code == 400


def test_feed_categories_are_counted_and_localized(api_client):
    phones = CategoryFactory(slug="phones", name_fr="Téléphones", name_ar="هواتف")
    cars = CategoryFactory(slug="cars", name_fr="Voitures", name_ar="سيارات")
    algiers = WilayaFactory(code="16", name_fr="Alger")
    ProductFactory(category=phones, wilaya=algiers)
    ProductFactory(category=phones)
    ProductFactory(category=cars)

    response = api_client.get(CATEGORIES_URL)

    assert response.status_code == 200
    assert [(row["slug"], row["count"]) for row in response.data] == [
        ("phones", 2),
        ("cars", 1),
    ]

    local = api_client.get(CATEGORIES_URL, {"wilaya": algiers.pk})
    assert [(row["slug"], row["count"]) for row in local.data] == [("phones", 1)]

    arabic = api_client.get(CATEGORIES_URL, HTTP_ACCEPT_LANGUAGE="ar")
    assert {row["slug"]: row["name"] for row in arabic.data}["phones"] == "هواتف"


def test_detail_view_increments_views_count(api_client):
    product = ProductFactory()

    response = api_client.get(f"/api/v1/products/{product.pk}/")

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.views_count == 1
    assert response.data["views_count"] == 1


def test_list_and_search_expose_views_count(api_client):
    product = ProductFactory(views_count=7)

    listed = api_client.get("/api/v1/products/")
    searched = api_client.get("/api/v1/search/")

    assert listed.data["results"][0]["views_count"] == 7
    assert searched.data["results"][0]["views_count"] == 7


def test_draft_detail_does_not_count_a_view(api_client):
    product = ProductFactory(status="DRAFT")

    api_client.get(f"/api/v1/products/{product.pk}/")

    product.refresh_from_db()
    assert product.views_count == 0
