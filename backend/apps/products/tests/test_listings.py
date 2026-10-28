"""Phase 13: listings — lifecycle, quotas, duplicates, slugs, wizard, guards.

One row is both a store SKU and an individual's classified (docs/todo.md
Phase 0 decision #2), so every test here says which half it means:

* ``listing_type`` branches behaviour — ``STORE_PRODUCT`` keeps the store,
  inventory and the Phase 6 cart path; everything else is contact-first;
* ``seller`` owns it for *everyone*: a classified needs no store, no
  ``is_seller`` flag and no store-scoped queryset;
* ``status`` gates what strangers see, and only
  :mod:`apps.products.lifecycle` may move it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from apps.orders.models import Cart, CartItem, Order
from apps.products.duplicates import TITLE_SIMILARITY, title_similarity
from apps.products.models import ContactMode, ListingStatus, ListingType, Product
from apps.users.plans import get_listing_quota
from tests.factories import (
    AddressFactory,
    AttributeDefinitionFactory,
    CartItemFactory,
    CategoryFactory,
    ProductFactory,
    UserFactory,
    WilayaFactory,
    default_category,
)

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"
CREATE_URL = "/api/v1/products/create/"
SELLER_LIST_URL = "/api/v1/products/seller/list/"
SELLER_CREATE_URL = "/api/v1/products/seller/create/"
QUOTA_URL = "/api/v1/products/seller/quota/"
WISHLIST_ADD_URL = "/api/v1/products/wishlist/add/"
CART_ADD_URL = "/api/v1/orders/cart/add/"
CHECKOUT_URL = "/api/v1/orders/checkout/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def draft_for(seller, **overrides):
    """A complete-but-unpublished classified owned by ``seller``.

    "Complete" means it passes :func:`apps.products.lifecycle.incomplete_fields`
    — the wizard's drafts are usually *not* complete, which is exactly what
    the leniency tests below are about.
    """
    defaults = {
        "store": None,
        "seller": seller,
        "listing_type": ListingType.FOR_SALE,
        "status": ListingStatus.DRAFT,
        "name": "Vélo de ville",
        "description": "Vélo en bon état, usage régulier.",
        "base_price": Decimal("15000.00"),
        "category": default_category(),
        "wilaya": WilayaFactory(),
    }
    defaults.update(overrides)
    return ProductFactory(**defaults)


def wizard_payload(**overrides):
    """A minimal first-step body for ``POST /products/create/``."""
    data = {
        "category_id": default_category().id,
        "name": "Vélo de ville",
        "description": "Vélo en bon état.",
        "base_price": "15000.00",
        "wilaya_id": WilayaFactory().id,
        "listing_type": ListingType.FOR_SALE,
        "contact_mode": ContactMode.PHONE,
    }
    data.update(overrides)
    return data


def act(client, product, action, **body):
    """POST one lifecycle action at the listing's lifecycle endpoint."""
    return client.post(
        f"{LIST_URL}{product.pk}/lifecycle/", {"action": action, **body}, format="json"
    )


def fill_cart(buyer, product, quantity=1):
    cart, _ = Cart.objects.get_or_create(user=buyer)
    return CartItemFactory(
        cart=cart,
        product=product,
        quantity=quantity,
        price_at_time_of_addition=product.base_price,
    )


# ---------------------------------------------------------------------------
# Lifecycle state machine (apps/products/lifecycle.py)
# ---------------------------------------------------------------------------
def test_publish_takes_a_complete_draft_live(seller_client, seller):
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.ACTIVE
    assert draft.slug == "velo-de-ville"
    assert draft.published_at is not None
    assert draft.expires_at and draft.expires_at > timezone.now()
    body = response.data
    assert body["status"] == "ACTIVE"
    assert body["status_label"]  # the translated twin rides along
    assert body["canonical_path"] == f"/l/{draft.slug}-{draft.pk}"


def test_publish_answers_with_exactly_what_is_missing(seller_client, seller):
    draft = draft_for(seller, wilaya=None)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 400
    assert response.data["code"] == "incomplete_listing"
    assert response.data["details"]["missing"] == ["wilaya"]
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT  # nothing half-applied


def test_autosave_is_lenient_but_publish_enforces_required_attributes(buyer_client):
    category = CategoryFactory()
    AttributeDefinitionFactory(category=category, key="storage", required=True, type="text")
    payload = wizard_payload(
        category_id=category.id, attributes_json={}, contact_mode=ContactMode.PHONE
    )

    created = buyer_client.post(CREATE_URL, payload, format="json")
    assert created.status_code == 201  # a half-filled draft may be saved…

    response = act(buyer_client, Product.objects.get(pk=created.data["id"]), "publish")

    assert response.status_code == 400  # …but not published
    assert response.data["code"] == "invalid_attributes"
    assert response.data["details"]["errors"]


def test_unknown_action_is_rejected(seller_client, seller):
    draft = draft_for(seller)

    response = act(seller_client, draft, "self_destruct")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_transition"
    assert "publish" in response.data["details"]["allowed"]
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT


def test_illegal_transition_leaves_the_row_untouched(seller_client, seller):
    listing = ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE)
    published_at = listing.published_at

    response = act(seller_client, listing, "renew")  # renew only fits EXPIRED

    assert response.status_code == 400
    assert response.data["code"] == "invalid_transition"
    assert response.data["details"] == {"status": "ACTIVE", "action": "renew"}
    listing.refresh_from_db()
    assert listing.status == ListingStatus.ACTIVE
    assert listing.published_at == published_at


def test_mark_sold_stamps_the_time_and_takes_it_off_the_catalogue(seller_client, seller, client):
    listing = ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE)

    response = act(seller_client, listing, "mark_sold")

    assert response.status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.SOLD
    assert listing.sold_at is not None
    # Gone for strangers the moment it is sold…
    assert client.get(f"{LIST_URL}{listing.pk}/").status_code == 404
    # …and relisting gives it a fresh window, with no stale sold_at.
    assert act(seller_client, listing, "relist").status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.ACTIVE
    assert listing.sold_at is None
    assert listing.expires_at and listing.expires_at > timezone.now()


def test_renew_reopens_an_expired_listing_with_a_fresh_window(seller_client, seller):
    expired = draft_for(
        seller,
        status=ListingStatus.EXPIRED,
        published_at=timezone.now() - timedelta(days=60),
        expires_at=timezone.now() - timedelta(days=30),
    )

    response = act(seller_client, expired, "renew")

    assert response.status_code == 200
    expired.refresh_from_db()
    assert expired.status == ListingStatus.ACTIVE
    assert expired.expires_at and expired.expires_at > timezone.now()


def test_archive_round_trip_hides_then_restores_the_row(seller_client, seller, client):
    listing = ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE)

    assert act(seller_client, listing, "archive").status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.ARCHIVED
    assert client.get(f"{LIST_URL}{listing.pk}/").status_code == 404

    assert act(seller_client, listing, "unarchive").status_code == 200
    listing.refresh_from_db()
    # Unarchived lands on DRAFT, not ACTIVE: republishing is a new decision
    # (fresh completeness/quota/duplicate gates), never a silent resurrection.
    assert listing.status == ListingStatus.DRAFT
    assert client.get(f"{LIST_URL}{listing.pk}/").status_code == 404


def test_strangers_cannot_drive_the_lifecycle(buyer_client, seller):
    draft = draft_for(seller)

    response = act(buyer_client, draft, "publish")

    assert response.status_code == 404
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT


@override_settings(LISTINGS_REQUIRE_MODERATION=True)
def test_publishing_waits_for_moderation_when_required(seller_client, seller):
    """Phase 17 flips this setting, not a code path: publish walks the
    ``PENDING_REVIEW`` edge and stops there until approve/reject runs."""
    draft = draft_for(seller)

    assert act(seller_client, draft, "publish").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.PENDING_REVIEW

    assert act(seller_client, draft, "withdraw").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT

    assert act(seller_client, draft, "publish").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.PENDING_REVIEW

    assert act(seller_client, draft, "reject").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.REJECTED

    # A rejection is not an end state: fix it, publish again.
    assert act(seller_client, draft, "publish").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.PENDING_REVIEW

    assert act(seller_client, draft, "approve").status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.ACTIVE


# ---------------------------------------------------------------------------
# Quotas (apps/users/plans.py)
# ---------------------------------------------------------------------------
@override_settings(MAX_ACTIVE_LISTINGS_PER_USER=2)
def test_the_free_tier_caps_publishing(seller_client, seller):
    for _ in range(2):
        ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE)
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 400
    assert response.data["code"] == "quota_reached"
    assert response.data["details"] == {"quota": 2, "active": 2}
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT  # drafts are free; publish is not


def test_phone_verification_triples_the_free_tier():
    plain = UserFactory()
    verified = UserFactory(phone_verified_at=timezone.now())

    with override_settings(MAX_ACTIVE_LISTINGS_PER_USER=10):
        assert get_listing_quota(plain) == 10
        assert get_listing_quota(verified) == 30


def test_a_store_owner_is_never_below_the_store_tier(seller, store):
    """Activating a store can only raise the ceiling — the two caps are
    monotonic instead of fighting each other."""
    with override_settings(MAX_ACTIVE_LISTINGS_PER_USER=2, MAX_PRODUCTS_PER_SELLER=20):
        assert get_listing_quota(UserFactory()) == 2  # no store: the raw tier
        assert get_listing_quota(seller) == 20  # store floor wins


def test_paid_plans_are_unlimited():
    user = UserFactory()
    assert get_listing_quota(user) == 10

    # Phase 21 persists plans; today ``get_plan`` reads the attribute, which
    # is the seam that billing will fill in.
    user.plan = "business"
    assert get_listing_quota(user) is None


@override_settings(MAX_DRAFT_LISTINGS=1)
def test_the_draft_cap_bounds_the_wizard(buyer_client):
    first = buyer_client.post(CREATE_URL, wizard_payload(), format="json")
    second = buyer_client.post(CREATE_URL, wizard_payload(), format="json")

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.data["code"] == "draft_limit"
    assert second.data["details"] == {"limit": 1, "drafts": 1}
    assert Product.objects.filter(seller=first.data["seller"]["id"]).count() == 1


def test_the_quota_endpoint_reports_every_number_the_ui_shows(seller_client, seller, store):
    ProductFactory(store=store, seller=seller)  # a live store SKU
    ProductFactory(store=None, seller=seller, status=ListingStatus.DRAFT)

    response = seller_client.get(QUOTA_URL)

    assert response.status_code == 200
    assert response.data == {
        "plan": "free",
        "active_listings": 1,
        "listing_quota": 20,  # max(free tier 10, store tier 20)
        "drafts": 1,
        "draft_limit": 20,
        "store_products": 1,
        "store_product_quota": 20,
    }


def test_the_quota_endpoint_for_someone_without_a_store(buyer_client, buyer):
    ProductFactory(store=None, seller=buyer, status=ListingStatus.ACTIVE)

    response = buyer_client.get(QUOTA_URL)

    assert response.status_code == 200
    assert response.data["active_listings"] == 1
    assert response.data["listing_quota"] == 10
    assert response.data["store_products"] == 0
    assert response.data["store_product_quota"] is None  # no store, no store cap


# ---------------------------------------------------------------------------
# Duplicate detection (apps/products/duplicates.py)
# ---------------------------------------------------------------------------
def test_publish_flags_the_same_ad_posted_twice(seller_client, seller):
    existing = ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        name="Vélo de ville",
        base_price=Decimal("15000.00"),
    )
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 400
    assert response.data["code"] == "possible_duplicate"
    assert response.data["details"]["duplicate_of"] == existing.pk
    assert response.data["details"]["duplicate_name"] == existing.name
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT


def test_confirmation_publishes_past_the_warning(seller_client, seller):
    ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        name="Vélo de ville",
        base_price=Decimal("15000.00"),
    )
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish", allow_duplicate=True)

    assert response.status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.ACTIVE


def test_allow_duplicate_never_bypasses_completeness(seller_client, seller):
    draft = draft_for(seller, wilaya=None)

    response = act(seller_client, draft, "publish", allow_duplicate=True)

    assert response.status_code == 400
    assert response.data["code"] == "incomplete_listing"


def test_a_distant_price_is_a_different_ad(seller_client, seller):
    ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        name="Vélo de ville",
        base_price=Decimal("15000.00"),
    )
    draft = draft_for(seller, base_price=Decimal("30000.00"))  # 100% away

    response = act(seller_client, draft, "publish")

    assert response.status_code == 200


def test_someone_elses_identical_ad_is_not_yours(seller_client, seller):
    """Duplicates are scoped to one seller's own catalogue: somebody else
    posting the same ad is competition, not a repost."""
    ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.ACTIVE,
        name="Vélo de ville",
        base_price=Decimal("15000.00"),
    )
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 200
    draft.refresh_from_db()
    assert draft.status == ListingStatus.ACTIVE


def test_a_classified_is_not_a_duplicate_of_the_store_sku(seller_client, store, seller):
    """The detector matches the *kind* of offer: variants are legitimate
    inside a catalogue, and a classified titled like a SKU is not a repost."""
    ProductFactory(
        store=store,
        seller=seller,
        status=ListingStatus.ACTIVE,
        name="Vélo de ville",
        base_price=Decimal("15000.00"),
    )
    draft = draft_for(seller)

    response = act(seller_client, draft, "publish")

    assert response.status_code == 200


def test_the_similarity_helper_sees_reworded_and_distinct_titles():
    assert title_similarity("Gaming laptop DELL", "dell gaming laptop") >= TITLE_SIMILARITY
    assert title_similarity("iPhone 13 Pro", "Samsung Galaxy S24") < TITLE_SIMILARITY
    assert title_similarity("", "") == 0.0


# ---------------------------------------------------------------------------
# Slug, canonical URL and the public surface
# ---------------------------------------------------------------------------
def test_a_published_listing_gets_its_canonical_url(seller_client, seller, api_client):
    draft = draft_for(seller)

    act(seller_client, draft, "publish")

    page = api_client.get(f"{LIST_URL}{draft.pk}/")
    assert page.status_code == 200
    assert page.data["slug"] == "velo-de-ville"
    assert page.data["canonical_path"] == f"/l/velo-de-ville-{draft.pk}"
    assert page.data["wilaya"] is not None  # location rides on the detail page


def test_renaming_a_live_listing_moves_the_slug(seller_client, seller):
    draft = draft_for(seller)
    act(seller_client, draft, "publish")

    response = seller_client.patch(
        f"{LIST_URL}seller/{draft.pk}/", {"name": "Vélo de course"}, format="json"
    )

    assert response.status_code == 200
    draft.refresh_from_db()
    assert draft.slug == "velo-de-course"
    assert draft.canonical_path == f"/l/velo-de-course-{draft.pk}"


def test_drafts_are_invisible_to_strangers(api_client, buyer_client, seller):
    draft = draft_for(seller)

    assert api_client.get(f"{LIST_URL}{draft.pk}/").status_code == 404
    assert api_client.get(f"{LIST_URL}{draft.pk}/similar/").status_code == 404
    listed = [row["id"] for row in api_client.get(LIST_URL).data["results"]]
    assert draft.pk not in listed
    wishlisted = buyer_client.post(WISHLIST_ADD_URL, {"product_id": draft.pk}, format="json")
    assert wishlisted.status_code == 404
    assert wishlisted.data["code"] == "product_not_found"


def test_the_detail_page_flips_expiry_lazily(api_client, seller):
    stale = draft_for(
        seller, status=ListingStatus.ACTIVE, expires_at=timezone.now() - timedelta(days=1)
    )

    first = api_client.get(f"{LIST_URL}{stale.pk}/")

    assert first.status_code == 200
    assert first.data["status"] == "EXPIRED"  # the flip happened on read
    stale.refresh_from_db()
    assert stale.status == ListingStatus.EXPIRED
    assert api_client.get(f"{LIST_URL}{stale.pk}/").status_code == 404


def test_similar_listings_follow_the_category_family_and_skip_own_rows(api_client, seller):
    root = CategoryFactory()
    phones = CategoryFactory(parent=root)
    tablets = CategoryFactory(parent=root)
    mine = ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        category=phones,
        name="Vélo de ville",
    )
    sibling = ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.ACTIVE,
        category=tablets,
        name="Vélo de course",
    )
    my_other = ProductFactory(
        store=None, seller=seller, status=ListingStatus.ACTIVE, category=phones, name="Autre vélo"
    )
    hidden = ProductFactory(
        store=None, seller=UserFactory(), status=ListingStatus.DRAFT, category=phones
    )
    unrelated = ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.ACTIVE,
        category=CategoryFactory(),
        name="Chaise de bureau",
    )

    response = api_client.get(f"{LIST_URL}{mine.pk}/similar/")

    assert response.status_code == 200
    ids = [row["id"] for row in response.data]
    assert sibling.pk in ids  # parent-or-sibling subtree
    assert my_other.pk not in ids  # own rows belong to "more from seller"
    assert hidden.pk not in ids  # drafts are not public
    assert unrelated.pk not in ids


def test_more_from_seller_shows_only_live_rows(api_client, seller):
    first = ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE, name="A")
    second = ProductFactory(store=None, seller=seller, status=ListingStatus.ACTIVE, name="B")
    draft = ProductFactory(store=None, seller=seller, status=ListingStatus.DRAFT, name="C")
    stranger = ProductFactory(store=None, seller=UserFactory(), name="D")

    response = api_client.get(f"{LIST_URL}{first.pk}/more-from-seller/")

    assert response.status_code == 200
    ids = [row["id"] for row in response.data]
    assert second.pk in ids
    assert first.pk not in ids  # never recommends the row you are looking at
    assert draft.pk not in ids
    assert stranger.pk not in ids


def test_the_catalogue_filters_by_wilaya(api_client):
    alger = WilayaFactory(code="16", name_fr="Alger", name_ar="الجزائر")
    oran = WilayaFactory(code="31", name_fr="Oran", name_ar="وهران")
    in_alger = ProductFactory(
        store=None, seller=UserFactory(), status=ListingStatus.ACTIVE, wilaya=alger
    )
    ProductFactory(store=None, seller=UserFactory(), status=ListingStatus.ACTIVE, wilaya=oran)
    ProductFactory(store=None, seller=UserFactory(), status=ListingStatus.ACTIVE)

    page = api_client.get(LIST_URL, {"wilaya": str(alger.pk)})

    assert [row["id"] for row in page.data["results"]] == [in_alger.pk]
    # Unknown or stale ids are an empty page, never a 500.
    assert api_client.get(LIST_URL, {"wilaya": "999999"}).data["results"] == []
    assert api_client.get(LIST_URL, {"wilaya": "abc"}).data["results"] == []


def test_classified_rows_keep_the_same_list_payload_keys(api_client, seller):
    classified = ProductFactory(
        store=None, seller=seller, status=ListingStatus.ACTIVE, wilaya=WilayaFactory()
    )
    sku = ProductFactory(status=ListingStatus.ACTIVE)  # with its own store

    rows = {row["id"]: row for row in api_client.get(LIST_URL).data["results"]}

    # One shape for the whole catalogue: the key is present on classifieds
    # and null, instead of silently absent (Phase 13, store is nullable).
    assert rows[classified.pk]["store_name"] is None
    assert rows[classified.pk]["store_slug"] is None
    assert rows[classified.pk]["seller_name"] == "Test User"
    assert rows[classified.pk]["wilaya_name"]
    assert rows[sku.pk]["store_name"]


# ---------------------------------------------------------------------------
# The seller's own surface
# ---------------------------------------------------------------------------
def test_every_kind_of_listing_lands_on_the_sellers_own_page(seller_client, seller, store):
    sku = ProductFactory(store=store, seller=seller)
    classified = ProductFactory(
        store=None, seller=seller, status=ListingStatus.DRAFT, name="Vélo de ville"
    )
    ProductFactory(store=None, seller=UserFactory(), name="Someone else's ad")

    response = seller_client.get(SELLER_LIST_URL)

    assert response.status_code == 200
    assert {row["id"] for row in response.data["results"]} == {sku.pk, classified.pk}


def test_the_status_filter_narrows_the_sellers_page(seller_client, seller, store):
    sku = ProductFactory(store=store, seller=seller)
    draft = ProductFactory(store=None, seller=seller, status=ListingStatus.DRAFT)

    drafts = seller_client.get(SELLER_LIST_URL, {"status": "DRAFT"})
    sold = seller_client.get(SELLER_LIST_URL, {"status": "SOLD"})
    nonsense = seller_client.get(SELLER_LIST_URL, {"status": "NOPE"})

    assert [row["id"] for row in drafts.data["results"]] == [draft.pk]
    assert sold.data["results"] == []
    assert nonsense.status_code == 400
    assert nonsense.data["details"]["status"]
    # No filter: everything, both kinds.
    assert len(seller_client.get(SELLER_LIST_URL).data["results"]) == 2
    assert sku.pk in {row["id"] for row in seller_client.get(SELLER_LIST_URL).data["results"]}


def test_an_individual_can_edit_and_delete_their_own_listing(buyer_client, buyer):
    """No store, no ``is_seller`` flag: ownership is the ``seller`` FK."""
    created = buyer_client.post(CREATE_URL, wizard_payload(), format="json")
    assert created.status_code == 201
    pk = created.data["id"]

    patched = buyer_client.patch(
        f"{LIST_URL}seller/{pk}/", {"name": "Vélo de course"}, format="json"
    )
    assert patched.status_code == 200
    assert Product.objects.get(pk=pk).name == "Vélo de course"

    deleted = buyer_client.delete(f"{LIST_URL}seller/{pk}/")
    assert deleted.status_code == 204
    assert not Product.objects.filter(pk=pk).exists()


def test_a_listing_type_cannot_be_rewritten(seller_client, product):
    assert product.listing_type == ListingType.STORE_PRODUCT

    response = seller_client.patch(
        f"{LIST_URL}seller/{product.pk}/", {"listing_type": "FOR_SALE"}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["details"]["listing_type"] == [
        "A listing's type cannot change after creation."
    ]
    product.refresh_from_db()
    assert product.listing_type == ListingType.STORE_PRODUCT


def test_autosave_echoing_the_unchanged_type_still_saves(buyer_client, buyer):
    """The wizard sends ``listing_type`` with *every* autosave payload.

    Echoing the value it already has is not a rewrite — refusing it would
    wedge the wizard on its second step boundary (the first save creates the
    draft, every later one PATCHes).
    """
    created = buyer_client.post(CREATE_URL, wizard_payload(), format="json")
    assert created.status_code == 201
    pk = created.data["id"]

    saved = buyer_client.patch(
        f"{LIST_URL}seller/{pk}/",
        {
            "listing_type": "FOR_SALE",
            "images": [{"image_url": "https://cdn.example.com/b.jpg"}],
        },
        format="json",
    )

    assert saved.status_code == 200
    assert saved.data["listing_type"] == "FOR_SALE"
    assert saved.data["images"][0]["image_url"] == "https://cdn.example.com/b.jpg"
    # …and the real change is still refused after the no-op path exists.
    changed = buyer_client.patch(
        f"{LIST_URL}seller/{pk}/", {"listing_type": "SERVICE"}, format="json"
    )
    assert changed.status_code == 400


def test_the_seller_phone_shows_only_when_invited(api_client, seller):
    listing = ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        listing_type=ListingType.FOR_SALE,
        contact_mode=ContactMode.PHONE,
        wilaya=WilayaFactory(),
    )
    seller.phone_number = "+213555123400"
    seller.phone_verified_at = timezone.now()
    seller.save(update_fields=["phone_number", "phone_verified_at"])

    # PHONE *is* the consent: a verified number is shown…
    assert api_client.get(f"{LIST_URL}{listing.pk}/").data["seller_phone"] == "+213555123400"

    # …until the seller switches to another contact mode…
    listing.contact_mode = ContactMode.CHAT
    listing.save(update_fields=["contact_mode", "updated_at"])
    assert api_client.get(f"{LIST_URL}{listing.pk}/").data["seller_phone"] is None

    # …or the number was never verified.
    listing.contact_mode = ContactMode.PHONE
    listing.save(update_fields=["contact_mode", "updated_at"])
    seller.phone_verified_at = None
    seller.save(update_fields=["phone_verified_at"])
    assert api_client.get(f"{LIST_URL}{listing.pk}/").data["seller_phone"] is None


# ---------------------------------------------------------------------------
# The wizard endpoint (POST /products/create/)
# ---------------------------------------------------------------------------
def test_the_wizard_creates_a_draft_owned_by_its_caller(buyer_client, buyer):
    response = buyer_client.post(CREATE_URL, wizard_payload(), format="json")

    assert response.status_code == 201
    data = response.data
    assert data["status"] == "DRAFT"
    assert data["listing_type"] == ListingType.FOR_SALE
    assert data["store"] is None
    assert data["seller"]["id"] == buyer.pk
    assert data["canonical_path"] == f"/l/_-{data['id']}"  # slug comes at publish
    row = Product.objects.get(pk=data["id"])
    assert row.seller_id == buyer.pk
    assert row.store_id is None
    assert row.status == ListingStatus.DRAFT
    assert row.slug is None


def test_the_wizard_refuses_to_open_a_store_sku(buyer_client, buyer):
    response = buyer_client.post(
        CREATE_URL, wizard_payload(listing_type=ListingType.STORE_PRODUCT), format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "wrong_listing_type"
    assert not Product.objects.filter(seller=buyer).exists()


def test_a_retried_wizard_save_returns_the_same_draft(buyer_client, buyer):
    payload = wizard_payload()

    first = buyer_client.post(CREATE_URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="wiz-1")
    second = buyer_client.post(CREATE_URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="wiz-1")

    assert first.status_code == second.status_code == 201
    assert second.data["id"] == first.data["id"]
    assert second["Idempotency-Replayed"] == "true"
    assert Product.objects.filter(seller=buyer).count() == 1

    # Same key, different body: a client bug, not a second listing.
    changed = buyer_client.post(
        CREATE_URL, wizard_payload(name="Autre vélo"), format="json", HTTP_IDEMPOTENCY_KEY="wiz-1"
    )
    assert changed.status_code == 409
    assert changed.data["code"] == "idempotency_key_conflict"
    assert Product.objects.filter(seller=buyer).count() == 1


def test_one_key_does_not_replay_across_create_endpoints(seller_client, seller, store):
    """``/products/create/`` (classifieds) and ``/products/seller/create/``
    (store SKUs) are distinct idempotency scopes: same user, same key, two
    different bodies must not answer each other."""
    store_payload = {
        "name": "Samsung Galaxy S24",
        "description": "Brand new sealed phone.",
        "base_price": "45000.00",
        "category_id": default_category().id,
    }

    on_store = seller_client.post(
        SELLER_CREATE_URL, store_payload, format="json", HTTP_IDEMPOTENCY_KEY="shared-key"
    )
    on_wizard = seller_client.post(
        CREATE_URL, wizard_payload(), format="json", HTTP_IDEMPOTENCY_KEY="shared-key"
    )

    # A cross-scope replay would have returned one cached body twice: two rows
    # of two different kinds prove neither request saw the other's response.
    assert on_store.status_code == 201
    assert on_wizard.status_code == 201
    assert Product.objects.filter(seller=seller).count() == 2
    assert (
        Product.objects.filter(seller=seller, listing_type=ListingType.STORE_PRODUCT).count() == 1
    )
    assert Product.objects.filter(seller=seller, listing_type=ListingType.FOR_SALE).count() == 1


# ---------------------------------------------------------------------------
# Expiry (manage.py expire_listings + the lazy read-time check)
# ---------------------------------------------------------------------------
def test_expire_listings_flips_due_rows_only_and_dry_run_is_inert(capsys):
    due = ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.ACTIVE,
        expires_at=timezone.now() - timedelta(hours=1),
    )
    fresh = ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.ACTIVE,
        expires_at=timezone.now() + timedelta(days=7),
    )
    draft = ProductFactory(
        store=None,
        seller=UserFactory(),
        status=ListingStatus.DRAFT,
        expires_at=timezone.now() - timedelta(days=1),
    )

    call_command("expire_listings", "--dry-run")
    assert "1 listing(s) would expire" in capsys.readouterr().out
    due.refresh_from_db()
    assert due.status == ListingStatus.ACTIVE  # dry-run changed nothing

    call_command("expire_listings")
    due.refresh_from_db()
    assert due.status == ListingStatus.EXPIRED
    fresh.refresh_from_db()
    assert fresh.status == ListingStatus.ACTIVE
    draft.refresh_from_db()
    assert draft.status == ListingStatus.DRAFT  # only ACTIVE rows are swept

    call_command("expire_listings")
    assert "Expired 0 listing(s)." in capsys.readouterr().out  # idempotent


# ---------------------------------------------------------------------------
# Cart / checkout guards (Phase 6 invariants under Phase 13)
# ---------------------------------------------------------------------------
def test_a_classified_cannot_enter_the_cart(buyer_client, buyer):
    classified = ProductFactory(
        store=None, seller=UserFactory(), status=ListingStatus.ACTIVE, wilaya=WilayaFactory()
    )

    response = buyer_client.post(
        CART_ADD_URL, {"product_id": classified.pk, "quantity": 1}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["details"]["product_id"]
    assert not CartItem.objects.filter(cart__user=buyer).exists()


def test_a_cart_line_for_a_sold_listing_cannot_be_updated(
    buyer_client, buyer, seller_client, product, inventory
):
    cart, _ = Cart.objects.get_or_create(user=buyer)
    line = CartItemFactory(
        cart=cart,
        product=product,
        quantity=1,
        price_at_time_of_addition=product.base_price,
    )
    assert act(seller_client, product, "mark_sold").status_code == 200

    response = buyer_client.put(
        f"/api/v1/orders/cart/items/{line.pk}/", {"quantity": 2}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "product_unavailable"
    line.refresh_from_db()
    assert line.quantity == 1


def test_checkout_refuses_a_listing_that_was_sold(
    buyer_client, buyer, address, seller_client, product, inventory
):
    fill_cart(buyer, product, quantity=2)
    assert act(seller_client, product, "mark_sold").status_code == 200

    response = buyer_client.post(
        CHECKOUT_URL,
        {"shipping_address_id": address.id, "shipping_method": "standard"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "product_unavailable"
    assert Order.objects.count() == 0
    inventory.refresh_from_db()
    assert inventory.stock_quantity == 10  # nothing reserved


def test_reusing_a_checkout_key_with_a_different_address_conflicts(
    buyer_client, buyer, address, product, inventory
):
    """Phase 13 (#14): a checkout replays on its payload, not on the key
    alone — the second request asked for a *different* order."""
    second_address = AddressFactory(user=buyer)
    payload = {"shipping_address_id": address.id, "shipping_method": "standard"}

    fill_cart(buyer, product, quantity=1)
    first = buyer_client.post(
        CHECKOUT_URL, payload, format="json", HTTP_IDEMPOTENCY_KEY="checkout-1"
    )
    assert first.status_code == 201

    fill_cart(buyer, product, quantity=1)
    conflict = buyer_client.post(
        CHECKOUT_URL,
        {**payload, "shipping_address_id": second_address.id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-1",
    )

    assert conflict.status_code == 409
    assert conflict.data["code"] == "idempotency_key_conflict"
    assert Order.objects.count() == 1  # charged exactly once
    inventory.refresh_from_db()
    assert inventory.stock_quantity == 9


def test_a_store_product_cannot_exist_without_a_store(buyer):
    """The DB, not only the API, refuses the unowned-SKU shape."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Product.objects.create(
                name="Unowned SKU",
                description="No store behind it.",
                base_price=Decimal("1.00"),
                seller=buyer,
                store=None,
                listing_type=ListingType.STORE_PRODUCT,
            )


# ---------------------------------------------------------------------------
# Query ceiling (finding #15: the seller list N+1)
# ---------------------------------------------------------------------------
def test_ten_listings_on_the_sellers_page_stay_constant(
    seller_client, store, django_assert_max_num_queries
):
    for index in range(10):
        if index % 2:
            ProductFactory(store=store, name=f"SKU {index}")
        else:
            ProductFactory(
                store=None,
                seller=store.owner,
                name=f"Classified {index}",
                status=ListingStatus.DRAFT if index == 0 else ListingStatus.ACTIVE,
                wilaya=WilayaFactory(),
            )

    # 1 page + count + one query per prefetch (images, attributes, inventory,
    # reviews). An un-joined FK or a per-row review lookup puts this well
    # above the ceiling, which is the point.
    with django_assert_max_num_queries(8):
        response = seller_client.get(SELLER_LIST_URL)

    assert response.status_code == 200
    assert len(response.data["results"]) == 10
