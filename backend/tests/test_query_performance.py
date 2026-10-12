"""Query ceilings and feed pagination (docs/todo.md Phase 10).

A list endpoint's cost has to be a *constant*: the number of queries a
20-row page costs must not depend on how many rows are on it. Every ceiling
below is asserted against a page of twenty so that a regression which
introduces per-row work (a property read, an unfiltered ``.filter()`` on a
prefetched relation) fails here instead of in production, where it would only
show up as latency.

The ceilings are deliberately a little above the queries each endpoint makes
today. They are a ratchet, not a stopwatch: they leave room for one or two
more joins (a new filter, a new sort) while still failing on anything that
scales with page size.
"""

from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.products.models import Product
from tests.factories import (
    CartFactory,
    InventoryFactory,
    OrderFactory,
    OrderItemFactory,
    ProductFactory,
    ProductImageFactory,
    ProductReviewFactory,
    StoreFactory,
    UserFactory,
    WishlistFactory,
)

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"
SEARCH_URL = "/api/v1/products/search/"
STORES_URL = "/api/v1/stores/"
ORDERS_URL = "/api/v1/orders/"
CART_URL = "/api/v1/orders/cart/"
WISHLIST_URL = "/api/v1/products/wishlist/"
AUDIT_URL = "/api/v1/inventory/audit-log/"
LOW_STOCK_URL = "/api/v1/inventory/low-stock/"
STATS_URL = "/api/v1/stores/seller/stats/"
ANALYTICS_URL = "/api/v1/stores/seller/analytics/"

PAGE_SIZE = 20


def build_catalogue(store, count=PAGE_SIZE):
    """``count`` products that are each a full row: an image and stock.

    Reviews are deliberately only given to the last one: the aggregate rides
    along in the SQL either way, and a review per product would mean a user
    per product, and password hashing dominates the runtime of this file.
    """
    products = []
    for index in range(count):
        product = ProductFactory(store=store, name=f"Catalogue {index:02d}")
        ProductImageFactory(product=product, is_primary=True, image_url=f"https://cdn/{index}.jpg")
        InventoryFactory(product=product, stock_quantity=10 + index)
        products.append(product)
    ProductReviewFactory(product=products[-1], user=UserFactory(), rating=4)
    return products


# ---------------------------------------------------------------------------
# The "Done when": a 20-row list renders in a bounded number of queries
# ---------------------------------------------------------------------------
def test_product_list_20_rows_is_a_constant_number_of_queries(
    api_client, django_assert_max_num_queries
):
    store = StoreFactory()
    build_catalogue(store)

    # 1 count for the page, 1 for the page itself (whose stock and rating
    # subqueries and wishlist Exists ride along), 1 for the image prefetch.
    with django_assert_max_num_queries(5):
        response = api_client.get(LIST_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE


def test_product_list_for_a_signed_in_buyer_stays_constant(
    buyer_client, buyer, django_assert_max_num_queries
):
    store = StoreFactory()
    products = build_catalogue(store)
    # The buyer wishlisted half of them: without the Exists annotation this
    # would be one EXISTS query per row.
    for product in products[: PAGE_SIZE // 2]:
        WishlistFactory(user=buyer, product=product)

    with django_assert_max_num_queries(5):
        response = buyer_client.get(LIST_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    wishlisted = {p["id"] for p in response.data["results"] if p["is_wishlisted"]}
    assert len(wishlisted) == PAGE_SIZE // 2


def test_search_in_stock_is_constant(buyer_client, django_assert_max_num_queries):
    store = StoreFactory()
    build_catalogue(store)  # every product has stock, so all of them match

    with django_assert_max_num_queries(5):
        response = buyer_client.get(SEARCH_URL, {"in_stock": "true", "page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE


def test_store_list_20_rows_is_constant(api_client, django_assert_max_num_queries):
    for _ in range(PAGE_SIZE):
        StoreFactory()

    # count + page; the embedded owner and the product count ride along.
    with django_assert_max_num_queries(4):
        response = api_client.get(STORES_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE
    assert response.data["results"][0]["product_count"] == 0


def test_wishlist_20_rows_is_constant(buyer_client, buyer, django_assert_max_num_queries):
    products = build_catalogue(StoreFactory())
    for product in products:
        WishlistFactory(user=buyer, product=product)

    # count + page + one image prefetch for the whole page.
    with django_assert_max_num_queries(5):
        response = buyer_client.get(WISHLIST_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE


def test_order_list_with_two_lines_each_is_constant(
    buyer_client, buyer, address, django_assert_max_num_queries
):
    store = StoreFactory()
    for _ in range(PAGE_SIZE):
        # One shared address: a per-order AddressFactory would mean a user
        # per order, and hashing those passwords is most of this file's time.
        order = OrderFactory(user=buyer, store=store, shipping_address=address)
        OrderItemFactory(order=order, product=ProductFactory(store=store))
        OrderItemFactory(order=order, product=ProductFactory(store=store))

    # count + page + the items and their products.
    with django_assert_max_num_queries(6):
        response = buyer_client.get(ORDERS_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE
    assert all(len(order["items"]) == 2 for order in response.data["results"])


def test_cart_with_ten_lines_is_constant(buyer_client, buyer, django_assert_max_num_queries):
    store = StoreFactory()
    cart = CartFactory(user=buyer)
    for index in range(10):
        product = ProductFactory(store=store, name=f"Cart line {index}")
        InventoryFactory(product=product, stock_quantity=5)
        cart.items.create(product=product, quantity=1, price_at_time_of_addition=product.base_price)

    with django_assert_max_num_queries(6):
        response = buyer_client.get(CART_URL)

    assert response.status_code == 200
    assert len(response.data["items"]) == 10
    assert response.data["items"][0]["product"]["total_stock"] == 5


def test_audit_log_20_rows_is_constant(seller_client, store, django_assert_max_num_queries):
    from apps.inventory.models import InventoryAuditLog

    for _ in range(PAGE_SIZE):
        InventoryAuditLog.objects.create(
            product=ProductFactory(store=store),
            quantity_delta=1,
            action_type="RESTOCK",
            previous_quantity=0,
            new_quantity=1,
        )

    # count + page; the serializer's product/inventory joins ride along.
    with django_assert_max_num_queries(4):
        response = seller_client.get(AUDIT_URL, {"page_size": PAGE_SIZE})

    assert response.status_code == 200
    assert len(response.data["results"]) == PAGE_SIZE


def test_low_stock_items_is_one_query(seller_client, store, django_assert_max_num_queries):
    for index in range(PAGE_SIZE):
        InventoryFactory(product=ProductFactory(store=store), stock_quantity=index)

    with django_assert_max_num_queries(2):
        response = seller_client.get(LOW_STOCK_URL)

    assert response.status_code == 200
    # stock 0 is out of stock, not *low* stock; 1..5 (the default threshold)
    # are low; 6+ are not.
    assert len(response.data) == 5


# ---------------------------------------------------------------------------
# The aggregates are right, not merely cheap
# ---------------------------------------------------------------------------
def test_catalog_stats_sum_every_inventory_row(api_client, store):
    """A product's stock is the sum of its variants, and ratings are averaged."""
    product = ProductFactory(store=store, name="Two variants", low_stock_threshold=5)
    InventoryFactory(product=product, stock_quantity=4, attribute_config={"size": "S"})
    InventoryFactory(product=product, stock_quantity=6, attribute_config={"size": "L"})
    ProductReviewFactory(product=product, user=UserFactory(), rating=5)
    ProductReviewFactory(product=product, user=UserFactory(), rating=1)

    response = api_client.get(LIST_URL)
    row = next(p for p in response.data["results"] if p["id"] == product.id)

    # Cross-multiplication between the inventory and review joins would have
    # reported 20 (4+6 twice), so this pins the subquery form down.
    assert row["total_stock"] == 10
    assert row["review_count"] == 2
    assert row["average_rating"] == pytest.approx(3.0)


def test_catalog_stats_for_a_product_without_variants_or_reviews(api_client, store):
    product = ProductFactory(store=store)

    response = api_client.get(LIST_URL)
    row = next(p for p in response.data["results"] if p["id"] == product.id)

    assert row["total_stock"] == 0
    assert row["review_count"] == 0
    assert row["average_rating"] == 0.0


def test_low_stock_threshold_boundary_is_unchanged(seller_client, store):
    """``is_low`` is still "at or below this product's own threshold"."""
    at_threshold = ProductFactory(store=store, low_stock_threshold=5)
    InventoryFactory(product=at_threshold, stock_quantity=5)
    above = ProductFactory(store=store, low_stock_threshold=5)
    InventoryFactory(product=above, stock_quantity=6)

    response = seller_client.get(LOW_STOCK_URL)
    ids = {row["product"] for row in response.data}

    assert ids == {at_threshold.id}


# ---------------------------------------------------------------------------
# Cursor (keyset) pagination
# ---------------------------------------------------------------------------
def test_feed_page_shape_is_next_previous_results(api_client, store):
    build_catalogue(store, count=3)

    response = api_client.get(LIST_URL, {"page_size": 2})

    assert response.status_code == 200
    assert set(response.data) == {"next", "previous", "results"}
    assert response.data["next"] is not None
    assert response.data["previous"] is None
    assert len(response.data["results"]) == 2


def test_cursor_walk_returns_every_row_once(api_client, store):
    """Following ``next`` walks the whole feed without repeats or gaps."""
    store.products.all().delete()
    products = build_catalogue(store, count=25)
    expected = {product.id for product in products}

    seen, url, pages = set(), LIST_URL + "?page_size=10", 0
    while url and pages < 10:
        page = api_client.get(url).data
        page_ids = {row["id"] for row in page["results"]}
        assert not seen & page_ids, "a cursor page repeated a row"
        seen |= page_ids
        url = page["next"]
        pages += 1

    assert seen == expected
    assert pages == 3  # 10 + 10 + 5


def test_page_size_is_capped_at_the_paginator_maximum():
    """A client asking for 10 000 rows gets at most 100."""
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from core.pagination import FeedCursorPagination

    request = Request(APIRequestFactory().get(LIST_URL, {"page_size": 10_000}))

    assert FeedCursorPagination().get_page_size(request) == 100


def test_invalid_cursor_is_a_404_in_the_standard_envelope(api_client):
    """DRF answers an undecodable cursor with NotFound, not a 400.

    That is its shipped behaviour, and the envelope must not paper over it:
    the code stays the one DRF attached (``not_found``) and the message is
    the translated ``invalid_cursor_message``.
    """
    response = api_client.get(LIST_URL, {"cursor": "not-a-cursor"})

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert response.data["request_id"]
    assert response.data["details"] is None


def test_offset_query_params_are_ignored_by_the_feed(api_client, store):
    """``?page=2`` no longer means anything here, and must not 500."""
    build_catalogue(store, count=3)

    response = api_client.get(LIST_URL, {"page": 2})

    assert response.status_code == 200
    assert len(response.data["results"]) == 3


# ---------------------------------------------------------------------------
# store_analytics: reachable (it existed but was never routed) and real
# ---------------------------------------------------------------------------
def test_store_analytics_is_routed_and_aggregates_real_rows(seller_client, store):
    product = ProductFactory(store=store, name="Charted", category="electronics")
    other_category = ProductFactory(store=store, name="Elsewhere", category="home")
    order = OrderFactory(store=store, payment_status="SUCCESSFUL")
    OrderItemFactory(order=order, product=product, quantity=3, unit_price_at_purchase=Decimal("50"))
    OrderItemFactory(order=order, product=other_category, quantity=1)

    response = seller_client.get(ANALYTICS_URL)

    assert response.status_code == 200
    assert [row["name"] for row in response.data["top_products"]] == ["Charted", "Elsewhere"]
    assert response.data["top_products"][0]["sales"] == 3
    assert response.data["top_products"][0]["revenue"] == 150.0
    assert sum(row["percentage"] for row in response.data["category_breakdown"]) == pytest.approx(
        100.0
    )
    # The time-series are empty until the analytics phase: an empty array is
    # a fact, a fabricated one is a lie with a date on it.
    assert response.data["revenue_trend"] == []
    assert response.data["orders_trend"] == []


def test_store_analytics_ignores_unpaid_orders(seller_client, store):
    product = ProductFactory(store=store)
    order = OrderFactory(store=store, payment_status="FAILED")
    OrderItemFactory(order=order, product=product, quantity=9)

    response = seller_client.get(ANALYTICS_URL)

    assert response.data["top_products"] == []


def test_store_analytics_requires_a_store(buyer_client):
    response = buyer_client.get(ANALYTICS_URL)

    assert response.status_code == 404
    assert response.data["code"] == "store_not_found"


def test_store_stats_counts_low_stock_in_sql(seller_client, store):
    low = ProductFactory(store=store, low_stock_threshold=5)
    InventoryFactory(product=low, stock_quantity=5)
    plenty = ProductFactory(store=store, low_stock_threshold=5)
    InventoryFactory(product=plenty, stock_quantity=50)
    empty = ProductFactory(store=store)

    response = seller_client.get(STATS_URL)

    assert response.status_code == 200
    assert response.data["total_products"] == 3
    assert response.data["low_stock_products"] == 2  # at threshold + out of stock


# ---------------------------------------------------------------------------
# Un-annotated use is a loud failure, not a slow one
# ---------------------------------------------------------------------------
def test_reading_the_stats_off_an_unannotated_queryset_raises():
    """The properties are gone; a silent per-row query would be the defect."""
    product = ProductFactory()

    for field in ("total_stock", "average_rating", "review_count", "is_low_stock"):
        assert not hasattr(product, field), f"{field} came back as a per-row property"


def test_queryset_helpers_are_available_where_serializers_read_them():
    annotated = Product.objects.with_catalog_stats().for_user(UserFactory())
    assert "total_stock" in annotated.query.annotations
    assert "average_rating" in annotated.query.annotations
    assert "review_count" in annotated.query.annotations
    assert "is_wishlisted" in annotated.query.annotations

    anonymous = Product.objects.for_user(None)
    assert "is_wishlisted" in anonymous.query.annotations


def test_for_user_annotations_only_the_callers_wishlist(buyer, store):
    mine = ProductFactory(store=store)
    WishlistFactory(user=buyer, product=mine)
    WishlistFactory(user=UserFactory(), product=ProductFactory(store=store))

    flagged = {p.id for p in Product.objects.for_user(buyer) if p.is_wishlisted}

    assert flagged == {mine.id}


def test_products_with_stock_annotates_every_inventory_row(store):
    product = ProductFactory(store=store)
    InventoryFactory(product=product, stock_quantity=3, attribute_config={"a": 1})
    InventoryFactory(product=product, stock_quantity=7, attribute_config={"a": 2})

    assert Product.objects.with_stock().get(id=product.id).total_stock == 10


def test_is_low_reads_the_annotated_total(store):
    product = ProductFactory(store=store, low_stock_threshold=5)
    InventoryFactory(product=product, stock_quantity=5)

    annotated = Product.objects.with_stock().get(id=product.id)

    assert annotated.is_low() is True
    assert annotated.is_low(total_stock=6) is False


def test_nested_product_queryset_is_what_prefetch_takes(buyer):
    """The helper is what order and cart lines nest with (apps.orders)."""
    from apps.products.models import nested_product_queryset

    prefetch = nested_product_queryset(buyer)

    assert prefetch.model is Product
    assert "images" in prefetch._prefetch_related_lookups
