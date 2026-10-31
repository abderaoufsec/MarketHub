"""Phase 14: uploaded photos on listings.

The media app owns "is this a real, safe, well-sized image?"; this module
owns everything after that: attaching an upload to a listing (or replacing
it), resolving which variant each surface gets, the implicit cover, and the
ownership rule (you can only attach your own uploads).
"""

from __future__ import annotations

import io

import pytest
from django.test import override_settings
from PIL import Image as PILImage

from apps.media.models import Image
from apps.products.models import Product, ProductImage
from tests.factories import ProductFactory, default_category

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"
CREATE_URL = "/api/v1/products/create/"
SELLER_CREATE_URL = "/api/v1/products/seller/create/"
UPLOAD_URL = "/api/v1/media/images/"
WISHLIST_URL = "/api/v1/products/wishlist/"


def make_photo(color=(90, 140, 200), size=(900, 700)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_photo(client, color=(90, 140, 200)) -> int:
    from django.core.files.uploadedfile import SimpleUploadedFile

    file = SimpleUploadedFile("photo.jpg", make_photo(color), "image/jpeg")
    response = client.post(UPLOAD_URL, {"file": file}, format="multipart")
    assert response.status_code == 201, response.data
    return response.data["id"]


def store_payload(**overrides):
    data = {
        "name": "Samsung Galaxy S24",
        "description": "Brand new sealed phone.",
        "base_price": "45000.00",
        "category_id": default_category().id,
    }
    data.update(overrides)
    return data


def wizard_payload(**overrides):
    from apps.products.models import ContactMode, ListingType
    from tests.factories import WilayaFactory

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


# ---------------------------------------------------------------------------
# Store SKU with uploads: the public surfaces
# ---------------------------------------------------------------------------
def test_store_product_with_uploads_exposes_card_variants(seller_client, seller, store):
    image_id = upload_photo(seller_client)

    created = seller_client.post(
        SELLER_CREATE_URL,
        store_payload(images=[{"upload_id": image_id}]),
        format="json",
    )

    assert created.status_code == 201, created.data
    product_id = Product.objects.get(store=store).pk

    feed = seller_client.get(LIST_URL).data["results"]
    card = next(row for row in feed if row["id"] == product_id)
    assert card["primary_image"].startswith("http://testserver/media/")
    assert card["primary_image"].endswith("/card.webp")
    assert card["primary_image_lqip"].startswith("data:image/webp;base64,")

    detail = seller_client.get(f"{LIST_URL}{product_id}/").data
    photo = detail["images"][0]
    assert photo["url"].startswith("http://testserver/media/")
    assert photo["url"].endswith("/card.webp")
    assert photo["full_url"].endswith("/full.webp")
    assert photo["upload_id"] == image_id
    assert photo["image_url"] == ""
    assert photo["lqip"].startswith("data:image/webp;base64,")
    assert photo["width"] == 900
    assert photo["height"] == 700


def test_wizard_create_accepts_uploads_and_defaults_the_cover(buyer_client, buyer):
    first = upload_photo(buyer_client, color=(200, 40, 40))
    second = upload_photo(buyer_client, color=(40, 200, 40))

    response = buyer_client.post(
        CREATE_URL,
        wizard_payload(images=[{"upload_id": first}, {"upload_id": second}]),
        format="json",
    )

    assert response.status_code == 201, response.data
    product = Product.objects.get(pk=response.data["id"])
    photos = list(product.images.order_by("sort_order", "id"))
    assert len(photos) == 2
    # The wizard never sends ``is_primary``: the first photo is the cover, or
    # every card would render the placeholder for a listing that has photos.
    assert [photo.is_primary for photo in photos] == [True, False]


def test_first_photo_is_the_cover_even_without_any_images_order(buyer_client):
    image_id = upload_photo(buyer_client)

    response = buyer_client.post(
        CREATE_URL, wizard_payload(images=[{"upload_id": image_id}]), format="json"
    )

    product = Product.objects.get(pk=response.data["id"])
    assert product.images.get().is_primary is True


# ---------------------------------------------------------------------------
# Replacing photos (the seller edit form)
# ---------------------------------------------------------------------------
def test_photos_can_be_replaced_on_update(seller_client, store):
    old = upload_photo(seller_client, color=(10, 10, 10))
    new = upload_photo(seller_client, color=(240, 240, 240))
    created = seller_client.post(
        SELLER_CREATE_URL, store_payload(images=[{"upload_id": old}]), format="json"
    )
    assert created.status_code == 201, created.data
    product_id = Product.objects.get(store=store).pk

    updated = seller_client.patch(
        f"/api/v1/products/seller/{product_id}/",
        {"images": [{"upload_id": new}]},
        format="json",
    )

    assert updated.status_code == 200, updated.data
    product = Product.objects.get(pk=product_id)
    assert list(product.images.values_list("upload_id", flat=True)) == [new]
    assert Image.objects.filter(pk=old).exists()  # the old upload is reusable


def test_a_listing_cannot_attach_someone_elses_upload(seller_client, buyer_client, store):
    foreign = upload_photo(buyer_client)

    response = seller_client.post(
        SELLER_CREATE_URL, store_payload(images=[{"upload_id": foreign}]), format="json"
    )

    assert response.status_code == 400
    assert "upload_id" in str(response.data["details"])
    assert not ProductImage.objects.filter(upload_id=foreign).exists()


def test_an_image_row_needs_a_source(buyer_client):
    response = buyer_client.post(CREATE_URL, wizard_payload(images=[{}]), format="json")

    assert response.status_code == 400
    assert "images" in response.data["details"]


def test_legacy_url_images_still_work(seller_client, store):
    response = seller_client.post(
        SELLER_CREATE_URL,
        store_payload(images=[{"image_url": "https://cdn.example.com/photo.jpg"}]),
        format="json",
    )

    assert response.status_code == 201, response.data
    row = seller_client.get(LIST_URL).data["results"][0]
    assert row["primary_image"] == "https://cdn.example.com/photo.jpg"
    assert row["primary_image_lqip"] == ""


@override_settings(MAX_IMAGES_PER_LISTING=2)
def test_the_image_cap_applies_to_uploads(seller_client, store):
    first = upload_photo(seller_client)
    second = upload_photo(seller_client, color=(1, 2, 3))

    response = seller_client.post(
        SELLER_CREATE_URL,
        store_payload(
            images=[
                {"upload_id": first},
                {"upload_id": second},
                {"upload_id": first},
            ]
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "images" in response.data["details"]


def test_wishlist_uses_the_card_variant(buyer_client, buyer, seller, store, seller_client):
    image_id = upload_photo(seller_client)
    created = seller_client.post(
        SELLER_CREATE_URL, store_payload(images=[{"upload_id": image_id}]), format="json"
    )
    product_id = Product.objects.get(store=store).pk
    buyer_client.post("/api/v1/products/wishlist/add/", {"product_id": product_id}, format="json")

    wishlist = buyer_client.get(WISHLIST_URL).data["results"]

    assert wishlist[0]["product_image"].startswith("http://testserver/media/")
    assert wishlist[0]["product_image"].endswith("/card.webp")


# ---------------------------------------------------------------------------
# Detaching: the photo survives, the attachment does not
# ---------------------------------------------------------------------------
def test_a_photo_can_be_removed_from_a_listing_but_kept_for_reuse(seller_client, store):
    image_id = upload_photo(seller_client)
    created = seller_client.post(
        SELLER_CREATE_URL, store_payload(images=[{"upload_id": image_id}]), format="json"
    )
    product_id = Product.objects.get(store=store).pk

    removed = seller_client.patch(
        f"/api/v1/products/seller/{product_id}/", {"images": []}, format="json"
    )

    assert removed.status_code == 200
    assert ProductImage.objects.filter(product_id=product_id).count() == 0
    assert Image.objects.filter(pk=image_id).exists()
