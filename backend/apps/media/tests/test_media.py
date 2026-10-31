"""Phase 14: the media pipeline — validation, EXIF stripping, variants, hashes.

Everything here drives the real pipeline (Pillow + numpy + Django storage),
with the bytes built in memory. The storage root is a per-test temp directory
(``conftest.isolated_media_root``), so "did the file land?" is a real
filesystem question, not a mock's promise.
"""

from __future__ import annotations

import io
import re
from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image as PILImage
from PIL import ImageChops

from apps.media.models import Image
from apps.media.phash import hamming, is_probable_match, phash
from apps.products.models import ProductImage
from tests.factories import ProductFactory, UserFactory

pytestmark = pytest.mark.django_db

UPLOAD_URL = "/api/v1/media/images/"
PRESIGN_URL = "/api/v1/media/images/presign/"
IMPORT_URL = "/api/v1/media/images/import/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_image(
    size: tuple[int, int] = (800, 600),
    color=(190, 40, 40),
    fmt: str = "JPEG",
    exif: PILImage.Exif | None = None,
    mode: str = "RGB",
) -> bytes:
    """Encoded image bytes, exactly as a browser would send them."""
    image = PILImage.new(mode, size, color)
    buffer = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def upload(client, data: bytes | None = None, *, name="photo.jpg", content_type="image/jpeg"):
    file = SimpleUploadedFile(name, data if data is not None else make_image(), content_type)
    return client.post(UPLOAD_URL, {"file": file}, format="multipart")


def stored(filename: str) -> PILImage.Image:
    with default_storage.open(filename, "rb") as handle:
        image = PILImage.open(io.BytesIO(handle.read()))
        image.load()
    return image


# ---------------------------------------------------------------------------
# Upload endpoint + storage
# ---------------------------------------------------------------------------
def test_upload_requires_authentication(api_client, db):
    response = upload(api_client)

    assert response.status_code == 401


def test_upload_processes_stores_and_returns_variant_urls(seller_client, seller):
    response = upload(seller_client, make_image((1600, 1200)))

    assert response.status_code == 201, response.data
    body = response.data
    assert body["width"] == 1600
    assert body["height"] == 1200
    assert body["status"] == Image.Status.READY
    assert body["url"].startswith("http://testserver/media/")
    assert body["url"].endswith("/full.webp")
    assert body["thumb_url"].endswith("/thumb.webp")
    assert body["card_url"].endswith("/card.webp")
    assert body["detail_url"].endswith("/detail.webp")

    image = Image.objects.get(pk=body["id"])
    assert image.owner == seller
    assert image.checksum
    assert re.fullmatch(r"[0-9a-f]{16}", image.phash)
    assert re.fullmatch(r"#[0-9a-f]{6}", image.dominant_color)
    assert image.lqip.startswith("data:image/webp;base64,")
    assert len(image.lqip) < 4000

    # Responsive widths, never upscaled, all real decodable files.
    assert stored(image.variants["thumb"]).width == 320
    assert stored(image.variants["card"]).width == 640
    assert stored(image.variants["detail"]).width == 1280
    assert stored(image.variants["full"]).width == 1600


def test_small_images_are_never_upscaled(seller_client):
    response = upload(seller_client, make_image((200, 100)))

    assert response.status_code == 201
    image = Image.objects.get(pk=response.data["id"])
    assert stored(image.variants["full"]).size == (200, 100)


def test_upload_strips_exif_and_applies_orientation(seller_client):
    exif = PILImage.Exif()
    exif[0x0112] = 6  # rotate 90°: a 120x80 photo became landscape
    exif.get_ifd(0x8825)[1] = "N"  # a GPS latitude, the privacy hazard
    exif.get_ifd(0x8825)[2] = (36.0, 42.0, 0.0)
    data = make_image((80, 120), color=(10, 140, 200), exif=exif)

    response = upload(seller_client, data)

    assert response.status_code == 201, response.data
    assert response.data["width"] == 120  # orientation applied
    assert response.data["height"] == 80

    image = Image.objects.get(pk=response.data["id"])
    source = stored(image.file.name)
    assert len(source.getexif()) == 0  # no EXIF at all
    assert 0x8825 not in source.getexif()  # no GPS IFD
    for variant in image.variants.values():
        assert len(stored(variant).getexif()) == 0


@pytest.mark.parametrize(
    ("fmt", "color", "name"),
    [
        ("PNG", (0, 160, 70), "shot.png"),
        ("WEBP", (30, 30, 200), "shot.webp"),
        ("GIF", (240, 200, 0), "shot.gif"),
    ],
)
def test_real_format_is_sniffed_not_trusted_from_the_name(seller_client, fmt, color, name):
    # A JPEG *filename* with PNG/WEBP/GIF bytes: the bytes decide.
    response = upload(seller_client, make_image(fmt=fmt, color=color), name="photo.jpg")

    assert response.status_code == 201, response.data
    image = Image.objects.get(pk=response.data["id"])
    assert stored(image.file.name).format == "JPEG"  # normalized source


def test_text_renamed_to_jpg_is_rejected(seller_client):
    response = upload(seller_client, b"this is definitely not an image", name="evil.jpg")

    assert response.status_code == 400
    assert response.data["code"] == "unsupported_image"
    assert Image.objects.count() == 0


def test_truncated_jpeg_header_is_rejected(seller_client):
    response = upload(seller_client, b"\xff\xd8\xff" + b"\x00" * 200)

    assert response.status_code == 400
    assert response.data["code"] == "unsupported_image"


@override_settings(MEDIA_MAX_UPLOAD_BYTES=5_000)
def test_oversized_upload_is_rejected_before_decoding(seller_client):
    response = upload(seller_client, make_image((900, 700)))

    assert response.status_code == 413
    assert response.data["code"] == "image_too_large"
    assert response.data["details"]["limit_bytes"] == 5_000


@override_settings(MEDIA_MIN_DIMENSION=300)
def test_too_small_dimensions_are_rejected(seller_client):
    response = upload(seller_client, make_image((200, 200)))

    assert response.status_code == 400
    assert response.data["code"] == "image_dimensions"


@override_settings(MEDIA_MAX_DIMENSION=500)
def test_too_large_dimensions_are_rejected(seller_client):
    response = upload(seller_client, make_image((800, 600)))

    assert response.status_code == 400
    assert response.data["code"] == "image_dimensions"


def test_identical_bytes_are_a_retry_not_a_second_copy(seller_client, seller):
    data = make_image((400, 300))

    first = upload(seller_client, data)
    second = upload(seller_client, data)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert Image.objects.filter(owner=seller).count() == 1


def test_another_user_uploading_the_same_bytes_gets_their_own_row(
    seller_client, buyer_client, seller, buyer
):
    data = make_image((400, 300))

    first = upload(seller_client, data)
    second = upload(buyer_client, data)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.data["id"] != first.data["id"]
    assert Image.objects.count() == 2


# ---------------------------------------------------------------------------
# Malware-scan hook
# ---------------------------------------------------------------------------
def reject_everything(raw, mime, filename):
    return {"infected": True}


def explode(raw, mime, filename):
    raise RuntimeError("scanner unavailable")


scan_calls = []


def record_and_accept(raw, mime, filename):
    scan_calls.append((mime, filename))
    return None


@override_settings(MEDIA_SCAN_HOOK="apps.media.tests.test_media.reject_everything")
def test_scan_hook_rejection_blocks_the_upload(seller_client):
    response = upload(seller_client)

    assert response.status_code == 400
    assert response.data["code"] == "upload_rejected"
    assert Image.objects.count() == 0


@override_settings(MEDIA_SCAN_HOOK="apps.media.tests.test_media.explode")
def test_a_broken_scanner_fails_closed(seller_client):
    response = upload(seller_client)

    assert response.status_code == 400
    assert response.data["code"] == "upload_rejected"


@override_settings(MEDIA_SCAN_HOOK="apps.media.tests.test_media.record_and_accept")
def test_the_scan_hook_receives_the_sniffed_format_and_the_filename(seller_client):
    scan_calls.clear()

    response = upload(seller_client)

    assert response.status_code == 201, response.data
    assert scan_calls == [("image/jpeg", "photo.jpg")]


@override_settings(MEDIA_MAX_PIXELS=1_000)
def test_a_decompression_bomb_is_a_400_not_a_500(seller_client):
    # Pillow aborts inside ``open()`` past 2x the pixel limit; the API must
    # answer the documented code (a 500 here is a remote DoS probe).
    response = upload(seller_client, make_image((2000, 2000)))

    assert response.status_code == 400
    assert response.data["code"] == "image_dimensions"


def test_a_clean_scan_hook_lets_the_upload_through(seller_client):
    response = upload(seller_client)

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Watermark (opt-in)
# ---------------------------------------------------------------------------
def test_watermark_is_off_by_default(seller_client):
    response = upload(seller_client, make_image((640, 480), color=(255, 255, 255)))

    image = Image.objects.get(pk=response.data["id"])
    detail = stored(image.variants["detail"])
    corner = detail.crop((detail.width - 40, detail.height - 20, detail.width, detail.height))
    # A uniform white photo stays uniform when the mark is disabled. (WebP
    # re-encodes white as one *near*-white value; compare colours, not 255.)
    assert len(corner.getcolors(maxcolors=10_000)) == 1


@override_settings(MEDIA_WATERMARK=True)
def test_watermark_marks_the_detail_variant(seller_client):
    response = upload(seller_client, make_image((640, 480), color=(255, 255, 255)))

    image = Image.objects.get(pk=response.data["id"])
    detail = stored(image.variants["detail"])
    corner = detail.crop((detail.width - 60, detail.height - 26, detail.width, detail.height))
    # The wordmark paints multiple shades in the bottom-right corner.
    assert len(corner.getcolors(maxcolors=10_000)) > 1
    # ... and the thumbnail stays cheap to decode (no mark burned in at 320px).
    thumb = stored(image.variants["thumb"])
    assert thumb.size == (320, 240)


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------
def test_phash_survives_resize_and_recompression():
    original = PILImage.open(io.BytesIO(make_image((800, 600), color=(120, 80, 200))))
    resized = original.resize((400, 300), PILImage.Resampling.LANCZOS)

    assert hamming(phash(original), phash(resized)) <= 2
    assert is_probable_match(phash(original), phash(resized))


def test_phash_separates_unrelated_images():
    solid = PILImage.new("RGB", (400, 300), (255, 0, 0))
    blocks = PILImage.new("RGB", (400, 300), (0, 0, 0))
    for x in range(0, 400, 40):
        for y in range(0, 300, 40):
            if (x // 40 + y // 40) % 2:
                blocks.paste((255, 255, 255), (x, y, x + 40, y + 40))

    assert not is_probable_match(phash(solid), phash(blocks))
    assert hamming(phash(solid), phash(blocks)) > 20


def test_uploaded_phash_matches_the_pipeline_hash(seller_client):
    data = make_image((500, 400), color=(20, 120, 20))
    response = upload(seller_client, data)

    expected = phash(PILImage.open(io.BytesIO(data)))
    assert response.data["phash"] == expected


# ---------------------------------------------------------------------------
# Delete + orphan purge
# ---------------------------------------------------------------------------
def test_owner_deletes_an_image_and_its_files(seller_client):
    response = upload(seller_client)
    image = Image.objects.get(pk=response.data["id"])
    names = [image.file.name, *image.variants.values()]
    assert all(default_storage.exists(name) for name in names)

    deleted = seller_client.delete(f"{UPLOAD_URL}{image.pk}/")

    assert deleted.status_code == 204
    assert not Image.objects.filter(pk=image.pk).exists()
    assert not any(default_storage.exists(name) for name in names)


def test_a_stranger_gets_404_not_403(buyer_client, seller_client):
    image_id = upload(seller_client).data["id"]

    response = buyer_client.delete(f"{UPLOAD_URL}{image_id}/")

    assert response.status_code == 404
    assert Image.objects.filter(pk=image_id).exists()


def test_an_attached_image_cannot_be_deleted(seller, store, seller_client):
    response = upload(seller_client)
    image = Image.objects.get(pk=response.data["id"])
    product = ProductFactory(store=store)
    ProductImage.objects.create(product=product, upload=image, is_primary=True)

    deleted = seller_client.delete(f"{UPLOAD_URL}{image.pk}/")

    assert deleted.status_code == 409
    assert deleted.data["code"] == "image_in_use"


def test_purge_orphan_media_spares_attached_images_and_recent_ones(seller, store, seller_client):
    attached = Image.objects.get(pk=upload(seller_client).data["id"])
    ProductImage.objects.create(
        product=ProductFactory(store=store), upload=attached, is_primary=True
    )
    orphan = Image.objects.get(pk=upload(seller_client, make_image((300, 300))).data["id"])
    fresh = Image.objects.get(pk=upload(seller_client, make_image((320, 320))).data["id"])
    Image.objects.filter(pk=orphan.pk).update(created_at=timezone.now() - timedelta(days=2))

    call_command("purge_orphan_media", "--dry-run", stdout=io.StringIO())
    assert Image.objects.filter(pk=orphan.pk).exists()

    call_command("purge_orphan_media", stdout=io.StringIO())

    assert not Image.objects.filter(pk=orphan.pk).exists()
    assert not default_storage.exists(orphan.variants["card"])
    assert Image.objects.filter(pk=attached.pk).exists()
    assert Image.objects.filter(pk=fresh.pk).exists()


# ---------------------------------------------------------------------------
# Direct-upload (presign) + import
# ---------------------------------------------------------------------------
def test_presign_falls_back_to_the_multipart_endpoint_on_local_storage(seller_client):
    response = seller_client.post(
        PRESIGN_URL,
        {"filename": "photo.jpg", "content_type": "image/jpeg", "size": 900_000},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["mode"] == "direct"
    assert response.data["upload_url"] == UPLOAD_URL
    assert response.data["fields"] is None


@override_settings(MEDIA_MAX_UPLOAD_BYTES=1_000)
def test_presign_refuses_a_file_over_the_upload_limit(seller_client):
    response = seller_client.post(
        PRESIGN_URL,
        {"filename": "photo.jpg", "content_type": "image/jpeg", "size": 5_000},
        format="json",
    )

    assert response.status_code == 400
    assert "size" in str(response.data["details"])


def test_presign_refuses_a_non_image_content_type(seller_client):
    response = seller_client.post(
        PRESIGN_URL,
        {"filename": "doc.pdf", "content_type": "application/pdf", "size": 5_000},
        format="json",
    )

    assert response.status_code == 400
    assert "content_type" in str(response.data["details"])


@override_settings(AWS_STORAGE_BUCKET_NAME="markethub-media")
def test_presign_returns_bucket_fields_when_s3_is_configured(seller_client, monkeypatch):
    from apps.media import storage

    monkeypatch.setattr(
        storage,
        "s3_presign",
        lambda **kwargs: {
            "upload_url": "https://bucket.example.com",
            "object_key": f"uploads/{kwargs['filename']}",
            "fields": {"key": "uploads/photo.jpg", "policy": "signed"},
            "expires_in": 600,
        },
    )

    response = seller_client.post(
        PRESIGN_URL,
        {"filename": "photo.jpg", "content_type": "image/jpeg", "size": 900_000},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["mode"] == "s3"
    assert response.data["upload_url"] == "https://bucket.example.com"
    assert response.data["object_key"] == "uploads/photo.jpg"
    assert response.data["fields"]["policy"] == "signed"


def test_import_processes_an_object_uploaded_directly(seller_client, seller):
    key = default_storage.save("uploads/direct.jpg", io.BytesIO(make_image((600, 400))))

    response = seller_client.post(
        IMPORT_URL, {"key": key, "original_name": "camera.jpg"}, format="json"
    )

    assert response.status_code == 201, response.data
    image = Image.objects.get(pk=response.data["id"])
    assert image.owner == seller
    assert image.width == 600
    assert image.original_name == "camera.jpg"


def test_import_rejects_keys_outside_the_uploads_namespace(seller_client):
    default_storage.save("listings/private.jpg", io.BytesIO(make_image((300, 300))))

    response = seller_client.post(IMPORT_URL, {"key": "listings/private.jpg"}, format="json")

    assert response.status_code == 404
    assert response.data["code"] == "image_not_found"


def test_import_of_a_missing_object_is_404(seller_client):
    response = seller_client.post(IMPORT_URL, {"key": "uploads/nope.jpg"}, format="json")

    assert response.status_code == 404
    assert response.data["code"] == "image_not_found"
