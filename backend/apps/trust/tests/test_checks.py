"""Phase 17: automated pre-publish checks (apps.trust.checks)."""

from decimal import Decimal

import pytest

from apps.products.lifecycle import publish
from apps.products.models import ListingStatus, ListingType, PriceMode
from apps.trust.blocklists import add_entry
from apps.trust.checks import (
    SEVERITY_BLOCK,
    SEVERITY_INFO,
    SEVERITY_REVIEW,
    run_pre_publish_checks,
)
from apps.trust.models import BlocklistKind
from tests.factories import ImageFactory, ProductFactory, WilayaFactory, default_category

pytestmark = pytest.mark.django_db


def draft(seller, **overrides):
    defaults = {
        "store": None,
        "seller": seller,
        "listing_type": ListingType.FOR_SALE,
        "status": ListingStatus.DRAFT,
        "name": "Vélo de ville",
        "description": "Vélo en bon état, usage régulier, révisé cette année.",
        "base_price": Decimal("15000.00"),
        "category": default_category(),
        "price_mode": PriceMode.FIXED,
    }
    defaults.update(overrides)
    return ProductFactory(**defaults)


def codes(result):
    return {issue.code for issue in result.issues}


def has(result, code, severity):
    return any(issue.code == code and issue.severity == severity for issue in result.issues)


def test_clean_listing_has_no_findings(seller):
    result = run_pre_publish_checks(draft(seller))

    assert result.issues == []
    assert not result.blocking
    assert not result.should_review


def test_banned_keyword_blocks_publication(seller):
    result = run_pre_publish_checks(draft(seller, description="Je vends une arme à feu."))

    assert has(result, "banned_keyword", SEVERITY_BLOCK)
    assert result.blocking


def test_arabic_banned_keyword_is_matched(seller):
    result = run_pre_publish_checks(draft(seller, name="سلاح للبيع"))

    assert has(result, "banned_keyword", SEVERITY_BLOCK)


def test_contact_details_in_the_description_block_publication(seller):
    result = run_pre_publish_checks(
        draft(seller, description="Appelez-moi au 0555 12 34 56 pour plus de photos.")
    )

    issue = next(issue for issue in result.issues if issue.code == "contact_in_description")
    assert issue.severity == SEVERITY_BLOCK
    assert issue.details["phones"] == ["+213555123456"]


def test_a_numeric_serial_or_timestamp_is_not_a_phone_number(seller):
    # The E2E wizard stamps the title with ``Date.now()``; a scanner that
    # treats every 10-15 digit run as a contact would block real listings
    # ("E2E Ad 1795028006944" parsed as +1795028006944).
    result = run_pre_publish_checks(draft(seller, name="E2E Ad 1795028006944"))

    assert "contact_in_description" not in codes(result)


def test_scam_template_requires_review(seller):
    result = run_pre_publish_checks(
        draft(seller, description="Paiement à l'avance par Western Union uniquement.")
    )

    assert has(result, "scam_template", SEVERITY_REVIEW)
    assert result.should_review
    assert not result.blocking


def test_price_far_below_the_category_median_requires_review(seller):
    for index in range(5):
        ProductFactory(
            store=None,
            seller=seller,
            status=ListingStatus.ACTIVE,
            name=f"Peer {index}",
            base_price=Decimal("10000.00"),
            category=default_category(),
        )
    cheap = draft(seller, base_price=Decimal("1000.00"))

    result = run_pre_publish_checks(cheap)

    assert has(result, "price_anomaly", SEVERITY_REVIEW)


def test_price_checks_need_a_real_peer_group(seller):
    ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        base_price=Decimal("10000.00"),
        category=default_category(),
    )

    result = run_pre_publish_checks(draft(seller, base_price=Decimal("100.00")))

    assert "price_anomaly" not in codes(result)


def test_a_copied_description_is_recorded_as_info_only(seller):
    description = "Ceci est une description suffisamment longue et identique."
    ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        description=description,
        category=default_category(),
    )

    result = run_pre_publish_checks(draft(seller, description=description))

    assert has(result, "duplicate_text", SEVERITY_INFO)
    assert not result.blocking
    assert not result.should_review


def test_a_copied_photo_requires_review(seller):
    phash = "ff00ff00ff00ff00"
    other = ProductFactory(
        store=None,
        seller=seller,
        status=ListingStatus.ACTIVE,
        category=default_category(),
    )
    other.images.create(upload=ImageFactory(owner=seller, phash=phash))
    listing = draft(seller)
    listing.images.create(upload=ImageFactory(owner=seller, phash=phash))

    result = run_pre_publish_checks(listing)

    assert has(result, "duplicate_image", SEVERITY_REVIEW)


def test_a_blocklisted_seller_phone_blocks_publication(seller):
    seller.phone_number = "+213555999888"
    seller.save(update_fields=["phone_number"])
    add_entry(kind=BlocklistKind.PHONE, value="0555999888", reason="Banned")

    result = run_pre_publish_checks(draft(seller))

    assert has(result, "blocklisted_seller", SEVERITY_BLOCK)


def test_blocked_listing_never_reaches_the_moderation_queue(seller):
    listing = draft(
        seller,
        description="Drogue disponible, livraison rapide.",
        wilaya=WilayaFactory(),
    )

    with pytest.raises(Exception) as error:
        publish(listing)

    assert error.value.code == "listing_blocked"  # type: ignore[attr-defined]
    listing.refresh_from_db()
    assert listing.status == ListingStatus.DRAFT


def test_review_finding_parks_the_listing_even_when_moderation_is_off(seller, settings):
    settings.LISTINGS_REQUIRE_MODERATION = False
    listing = draft(
        seller,
        description="Paiement à l'avance par MoneyGram, merci.",
        wilaya=None,
    )
    # Publish needs a complete listing; give it the required location.
    from tests.factories import WilayaFactory

    listing.wilaya = WilayaFactory()
    listing.save(update_fields=["wilaya"])

    published = publish(listing)

    assert published.status == ListingStatus.PENDING_REVIEW
    assert "scam_template" in {flag["code"] for flag in published.moderation_flags}
