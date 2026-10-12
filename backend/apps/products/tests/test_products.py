"""Product catalogue: public browsing, search, seller CRUD, reviews, wishlist."""

import pytest
from django.test import override_settings

from apps.products.models import ProductReview
from tests.factories import (
    InventoryFactory,
    ProductFactory,
    ProductImageFactory,
    UserFactory,
    WishlistFactory,
)

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"
FEATURED_URL = "/api/v1/products/featured/"
SEARCH_URL = "/api/v1/products/search/"
SELLER_LIST_URL = "/api/v1/products/seller/list/"
SELLER_CREATE_URL = "/api/v1/products/seller/create/"
REVIEWS_CREATE_URL = "/api/v1/products/reviews/create/"
MY_REVIEWS_URL = "/api/v1/products/reviews/my-reviews/"
WISHLIST_URL = "/api/v1/products/wishlist/"
WISHLIST_ADD_URL = "/api/v1/products/wishlist/add/"


def product_payload(**overrides):
    data = {
        "name": "Samsung Galaxy S24",
        "description": "Brand new sealed phone.",
        "base_price": "45000.00",
        "category": "electronics",
        "is_available": True,
        "low_stock_threshold": 3,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------
def test_product_list_is_public(api_client, product, inventory):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    # Cursor-paginated (Phase 10), so pages carry no ``count`` — GitHub and
    # Stripe style. The page envelope itself is asserted in
    # tests/test_query_performance.py.
    assert len(response.data["results"]) == 1
    result = response.data["results"][0]
    assert result["name"] == product.name
    assert result["store_name"] == product.store.store_name
    assert result["total_stock"] == 10


def test_product_list_filters_by_category_and_price(api_client, store):
    ProductFactory(store=store, name="Cheap", category="electronics", base_price=100)
    ProductFactory(store=store, name="Pricey", category="fashion", base_price=900)

    by_category = api_client.get(LIST_URL, {"category": "electronics"})
    assert [p["name"] for p in by_category.data["results"]] == ["Cheap"]

    by_price = api_client.get(LIST_URL, {"min_price": 500, "max_price": 1000})
    assert [p["name"] for p in by_price.data["results"]] == ["Pricey"]


def test_product_list_search_param(api_client, store):
    ProductFactory(store=store, name="Gaming Laptop")
    ProductFactory(store=store, name="Coffee Maker")

    response = api_client.get(LIST_URL, {"search": "gaming"})

    assert response.status_code == 200
    assert [p["name"] for p in response.data["results"]] == ["Gaming Laptop"]


def test_product_list_hides_unavailable_and_inactive_store(api_client, store):
    ProductFactory(store=store, name="Hidden", is_available=False)
    closed = ProductFactory(store=store, name="From closed store")
    closed.store.is_active = False
    closed.store.save()

    response = api_client.get(LIST_URL)

    assert response.data["results"] == []


def test_product_detail_includes_images_and_reviews(api_client, product, buyer):
    ProductImageFactory(product=product, image_url="https://cdn.example.com/p.jpg")

    response = api_client.get(f"{LIST_URL}{product.id}/")

    assert response.status_code == 200
    assert response.data["images"][0]["image_url"] == "https://cdn.example.com/p.jpg"
    assert response.data["is_wishlisted"] is False
    assert response.data["reviews"] == []


def test_product_detail_404_for_unavailable(api_client, product):
    product.is_available = False
    product.save()

    response = api_client.get(f"{LIST_URL}{product.id}/")

    assert response.status_code == 404


def test_featured_products(api_client, store):
    first = ProductFactory(store=store, name="First")
    second = ProductFactory(store=store, name="Second")

    response = api_client.get(FEATURED_URL)

    assert response.status_code == 200
    assert {p["id"] for p in response.data} == {first.id, second.id}


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------
def test_search_by_query_category_and_price(api_client, store):
    ProductFactory(store=store, name="Galaxy S24", category="phones", base_price=45000)
    ProductFactory(store=store, name="Galaxy A15", category="phones", base_price=15000)
    ProductFactory(store=store, name="Desk Lamp", category="home", base_price=2000)

    response = api_client.get(SEARCH_URL, {"q": "galaxy", "category": "phones"})
    # Cursor-paginated like the catalogue (Phase 10): search used to return
    # every match in one unpaginated response.
    assert {p["name"] for p in response.data["results"]} == {"Galaxy S24", "Galaxy A15"}

    priced = api_client.get(SEARCH_URL, {"min_price": 20000})
    assert [p["name"] for p in priced.data["results"]] == ["Galaxy S24"]


def test_search_in_stock_filter(api_client, store):
    in_stock = ProductFactory(store=store, name="Has stock")
    InventoryFactory(product=in_stock, stock_quantity=3)
    ProductFactory(store=store, name="No stock")

    response = api_client.get(SEARCH_URL, {"in_stock": "true"})

    assert [p["name"] for p in response.data["results"]] == ["Has stock"]


# ---------------------------------------------------------------------------
# Seller CRUD
# ---------------------------------------------------------------------------
def test_seller_product_list_only_shows_own(seller_client, product):
    ProductFactory(name="Other seller product")  # belongs to a different store

    response = seller_client.get(SELLER_LIST_URL)

    assert response.status_code == 200
    names = [p["name"] for p in response.data["results"]]
    assert product.name in names
    assert "Other seller product" not in names


def test_seller_list_empty_for_buyer(buyer_client):
    response = buyer_client.get(SELLER_LIST_URL)

    assert response.status_code == 200
    assert response.data["count"] == 0


def test_seller_can_create_product(seller_client, seller, store):
    response = seller_client.post(SELLER_CREATE_URL, product_payload(), format="json")

    assert response.status_code == 201
    assert seller.store.products.count() == 1


def test_product_create_requires_store(seller_client, seller):
    """A seller flag without a store must not create products.

    docs/todo.md §0.3 #8 (fixed in Phase 6): this used to answer HTTP 500.
    """
    assert not hasattr(seller, "store")

    response = seller_client.post(SELLER_CREATE_URL, product_payload(), format="json")

    assert response.status_code == 403


def test_product_create_rejected_for_buyer(buyer_client):
    """docs/todo.md §0.3 #8 (fixed in Phase 6): 403, not 500."""
    response = buyer_client.post(SELLER_CREATE_URL, product_payload(), format="json")

    assert response.status_code == 403


def test_seller_can_update_and_delete_product(seller_client, product):
    updated = seller_client.put(
        f"{LIST_URL}seller/{product.id}/",
        product_payload(name="Renamed product"),
        format="json",
    )
    assert updated.status_code == 200
    product.refresh_from_db()
    assert product.name == "Renamed product"

    deleted = seller_client.delete(f"{LIST_URL}seller/{product.id}/")
    assert deleted.status_code == 204
    assert not type(product).objects.filter(pk=product.pk).exists()


def test_seller_cannot_touch_other_sellers_product(seller_client, product):
    other_product = ProductFactory(name="Not mine")

    assert (
        seller_client.put(
            f"{LIST_URL}seller/{other_product.id}/", product_payload(), format="json"
        ).status_code
        == 404
    )
    assert seller_client.delete(f"{LIST_URL}seller/{other_product.id}/").status_code == 404


@override_settings(MAX_PRODUCTS_PER_SELLER=1)
def test_free_plan_quota_blocks_extra_products(seller_client, store):
    ProductFactory(store=store)  # already at the free-plan limit

    response = seller_client.post(SELLER_CREATE_URL, product_payload(), format="json")

    assert response.status_code == 400
    # The quota rejection is a plain serializer ValidationError, so the Phase 9
    # envelope carries it: the quota sentence itself is the human message.
    assert response.data["code"] == "validation_error"
    assert "limit" in response.data["message"].lower()
    assert response.data["request_id"] == response["X-Request-ID"]


# ---------------------------------------------------------------------------
# Listing-create idempotency (Phase 9): a retried POST with the same
# Idempotency-Key must not publish a second listing.
# ---------------------------------------------------------------------------
def test_listing_create_replays_first_response_for_same_idempotency_key(
    seller_client, seller, store
):
    payload = product_payload()
    headers = {"HTTP_IDEMPOTENCY_KEY": "listing-retry-1"}

    first = seller_client.post(SELLER_CREATE_URL, payload, format="json", **headers)
    retry = seller_client.post(SELLER_CREATE_URL, payload, format="json", **headers)

    assert first.status_code == 201
    assert "Idempotency-Replayed" not in first
    assert retry.status_code == 201
    assert retry["Idempotency-Replayed"] == "true"
    assert retry.data == first.data, "a replay must return the original body verbatim"
    assert seller.store.products.count() == 1


def test_listing_idempotency_key_rejected_when_payload_differs(seller_client, seller, store):
    headers = {"HTTP_IDEMPOTENCY_KEY": "listing-retry-2"}

    first = seller_client.post(SELLER_CREATE_URL, product_payload(), format="json", **headers)
    assert first.status_code == 201

    retry = seller_client.post(
        SELLER_CREATE_URL, product_payload(name="Renamed listing"), format="json", **headers
    )

    assert retry.status_code == 409
    assert retry.data["code"] == "idempotency_key_conflict"
    assert retry.data["request_id"] == retry["X-Request-ID"]
    assert seller.store.products.count() == 1, "the conflicting retry must create nothing"


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
def test_review_list_shows_only_approved(buyer_client, product, buyer):
    from tests.factories import ProductReviewFactory

    ProductReviewFactory(product=product, user=buyer, rating=5)
    ProductReviewFactory(product=product, is_approved=False, comment="spam")

    response = buyer_client.get(f"{LIST_URL}{product.id}/reviews/")

    assert response.status_code == 200
    assert len(response.data["results"]) == 1


def test_create_review_and_duplicate_guard(buyer_client, product, buyer):
    payload = {"product": product.id, "rating": 4, "comment": "Solid phone."}

    first = buyer_client.post(REVIEWS_CREATE_URL, payload, format="json")
    assert first.status_code == 201

    duplicate = buyer_client.post(REVIEWS_CREATE_URL, payload, format="json")
    assert duplicate.status_code == 400
    # Phase 9 envelope: the old hand-rolled {"error": …, "review_id": …} body
    # is now a branchable code with the id in structured details.
    assert duplicate.data["code"] == "already_reviewed"
    assert (
        duplicate.data["details"]["review_id"]
        == ProductReview.objects.get(product=product, user=buyer).id
    )
    assert duplicate.data["request_id"] == duplicate["X-Request-ID"]

    check = buyer_client.get(f"{LIST_URL}{product.id}/check-review/")
    assert check.data["has_reviewed"] is True


def test_create_review_rejects_bad_rating(buyer_client, product):
    response = buyer_client.post(
        REVIEWS_CREATE_URL,
        {"product": product.id, "rating": 42, "comment": "nope"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "rating" in response.data["details"]


def test_my_reviews_lists_own_reviews(buyer_client, product, buyer):
    from tests.factories import ProductReviewFactory

    ProductReviewFactory(product=product, user=buyer, rating=3, comment="meh")

    listed = buyer_client.get(MY_REVIEWS_URL)

    assert listed.status_code == 200
    assert len(listed.data["results"]) == 1


def test_owner_can_delete_own_review(buyer_client, product, buyer):
    from tests.factories import ProductReviewFactory

    mine = ProductReviewFactory(product=product, user=buyer)

    deleted = buyer_client.delete(f"{LIST_URL}reviews/{mine.id}/")

    assert deleted.status_code == 204


@pytest.mark.xfail(
    reason="ProductReviewCreateSerializer.validate() rejects any review that "
    "already exists for this user, so an author can never edit their own "
    "review (found while writing the Phase 3 suite; fixed in Phase 17)",
    strict=True,
)
def test_owner_can_update_own_review(buyer_client, product, buyer):
    from tests.factories import ProductReviewFactory

    mine = ProductReviewFactory(product=product, user=buyer, rating=3, comment="meh")

    response = buyer_client.put(
        f"{LIST_URL}reviews/{mine.id}/",
        {"product": product.id, "rating": 5, "comment": "great"},
        format="json",
    )

    assert response.status_code == 200
    mine.refresh_from_db()
    assert mine.rating == 5


def test_cannot_update_other_users_review(buyer_client, product):
    from tests.factories import ProductReviewFactory

    foreign = ProductReviewFactory(product=product)

    response = buyer_client.put(
        f"{LIST_URL}reviews/{foreign.id}/",
        {"product": product.id, "rating": 1, "comment": "hijacked"},
        format="json",
    )

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.rating == 5


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------
def test_wishlist_flow(buyer_client, product):
    added = buyer_client.post(WISHLIST_ADD_URL, {"product_id": product.id}, format="json")
    assert added.status_code == 201

    again = buyer_client.post(WISHLIST_ADD_URL, {"product_id": product.id}, format="json")
    assert again.status_code == 200

    check = buyer_client.get(f"{LIST_URL}wishlist/check/{product.id}/")
    assert check.data["is_wishlisted"] is True

    listed = buyer_client.get(WISHLIST_URL)
    assert len(listed.data["results"]) == 1

    removed = buyer_client.delete(f"{LIST_URL}wishlist/remove/{product.id}/")
    assert removed.status_code == 200

    cleared = buyer_client.delete(f"{LIST_URL}wishlist/clear/")
    assert cleared.status_code == 200


def test_wishlist_add_requires_product(buyer_client):
    response = buyer_client.post(WISHLIST_ADD_URL, {}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "product_id_required"
    assert response.data["request_id"] == response["X-Request-ID"]


def test_wishlist_add_unknown_product_404(buyer_client):
    response = buyer_client.post(WISHLIST_ADD_URL, {"product_id": 999999}, format="json")

    assert response.status_code == 404
    assert response.data["code"] == "product_not_found"


def test_wishlist_remove_not_wishlisted_404(buyer_client, product):
    """Removing a product that was never wishlisted is the other hand-built
    404 this slice converted; it now answers with the envelope too."""
    response = buyer_client.delete(f"{LIST_URL}wishlist/remove/{product.id}/")

    assert response.status_code == 404
    assert response.data["code"] == "not_in_wishlist"


def test_wishlist_is_per_user(buyer_client, product, buyer):
    WishlistFactory(user=UserFactory(), product=product)

    response = buyer_client.get(WISHLIST_URL)

    assert response.status_code == 200
    assert response.data["results"] == []
