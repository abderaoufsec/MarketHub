"""Phase 17: verification, blocklists, reports, appeals and staff tooling."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.messaging.models import Report
from apps.products.models import ListingStatus, PriceMode, ProductReview
from apps.trust.blocklists import add_entry, is_blocklisted, normalize_value
from apps.trust.models import (
    AccountSanction,
    Appeal,
    BlocklistEntry,
    BlocklistKind,
    ModerationAuditLog,
    SellerVerification,
    VerificationStatus,
)
from apps.trust.reputation import compute_reputation, tier_for_user
from tests.factories import (
    ImageFactory,
    ProductFactory,
    ProductReviewFactory,
    SellerFactory,
    UserFactory,
    WilayaFactory,
    default_category,
)

pytestmark = pytest.mark.django_db

TRUST = "/api/v1/trust"
SAFETY = f"{TRUST}/safety-center/"
REPUTATION = f"{TRUST}/sellers/{{user_id}}/reputation/"
VERIFICATION = f"{TRUST}/verification/"
STORE_VERIFICATION = f"{TRUST}/store-verification/"
APPEALS = f"{TRUST}/appeals/"


@pytest.fixture
def staff_client(db):
    staff = UserFactory(is_staff=True)
    client = APIClient()
    client.force_authenticate(user=staff)
    client.user = staff
    return client


def phone_verified(user, phone="+213555000111"):
    user.phone_number = phone
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_number", "phone_verified_at"])
    return user


def classified(seller, **overrides):
    defaults = {
        "store": None,
        "seller": seller,
        "status": ListingStatus.ACTIVE,
        "category": default_category(),
        "base_price": Decimal("15000.00"),
    }
    defaults.update(overrides)
    return ProductFactory(**defaults)


# ---------------------------------------------------------------------------
# Safety centre & reputation
# ---------------------------------------------------------------------------
def test_safety_centre_is_public_and_localised(api_client):
    french = api_client.get(SAFETY, HTTP_ACCEPT_LANGUAGE="fr")
    english = api_client.get(SAFETY, HTTP_ACCEPT_LANGUAGE="en")
    arabic = api_client.get(SAFETY, HTTP_ACCEPT_LANGUAGE="ar")

    assert french.status_code == 200
    assert french.data["language"] == "fr"
    assert len(french.data["sections"]) >= 5
    assert english.data["title"] == "Safety centre"
    assert arabic.data["title"] == "مركز الأمان"


def test_reputation_tier_grows_with_approved_verifications(api_client):
    seller = phone_verified(SellerFactory())

    assert tier_for_user(seller) == "PHONE"
    payload = api_client.get(REPUTATION.format(user_id=seller.pk)).data
    assert payload["tier"] == "PHONE"
    assert payload["badges"][0]["code"] == "PHONE"

    SellerVerification.objects.create(
        user=seller, kind="IDENTITY", status=VerificationStatus.APPROVED
    )
    assert tier_for_user(seller) == "ID"

    SellerVerification.objects.create(user=seller, kind="STORE", status=VerificationStatus.APPROVED)
    assert tier_for_user(seller) == "STORE"


def test_a_pending_or_rejected_verification_grants_no_badge():
    seller = phone_verified(SellerFactory())
    SellerVerification.objects.create(user=seller, kind="IDENTITY", status="PENDING")
    SellerVerification.objects.create(user=seller, kind="STORE", status="REJECTED")

    assert tier_for_user(seller) == "PHONE"


def test_reputation_breakdown_is_transparent():
    seller = phone_verified(SellerFactory())
    payload = compute_reputation(seller, use_cache=False)

    assert 0 <= payload["score"] <= 100
    assert payload["breakdown"]["base"] == 20
    assert payload["breakdown"]["phone_verified"] == 15
    assert "reports_penalty" in payload["breakdown"]


# ---------------------------------------------------------------------------
# Seller verification workflow
# ---------------------------------------------------------------------------
def test_identity_verification_requires_a_verified_phone(buyer_client, buyer):
    image = ImageFactory(owner=buyer)

    response = buyer_client.post(
        VERIFICATION, {"document_image_id": image.pk, "document_type": "ID_CARD"}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "phone_verification_required"


def test_identity_verification_cannot_borrow_someone_elses_photo(buyer_client, buyer):
    image = ImageFactory(owner=UserFactory())
    phone_verified(buyer)

    response = buyer_client.post(VERIFICATION, {"document_image_id": image.pk}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_verified_identity_is_submitted_pending_and_staff_can_approve(
    buyer_client, buyer, staff_client
):
    phone_verified(buyer)
    image = ImageFactory(owner=buyer)

    submitted = buyer_client.post(
        VERIFICATION,
        {"document_image_id": image.pk, "document_type": "PASSPORT"},
        format="json",
    )

    assert submitted.status_code == 201
    assert submitted.data["status"] == "PENDING"
    assert tier_for_user(buyer) == "PHONE"

    approval = staff_client.post(
        f"{TRUST}/admin/verifications/{submitted.data['id']}/action/",
        {"action": "approve"},
        format="json",
    )

    assert approval.status_code == 200
    assert approval.data["status"] == "APPROVED"
    assert tier_for_user(buyer) == "ID"
    assert ModerationAuditLog.objects.filter(action="VERIFICATION_APPROVED").exists()


def test_rejected_verification_keeps_the_reason_and_can_be_resubmitted(
    buyer_client, buyer, staff_client
):
    phone_verified(buyer)
    image = ImageFactory(owner=buyer)
    submitted = buyer_client.post(VERIFICATION, {"document_image_id": image.pk}, format="json")

    staff_client.post(
        f"{TRUST}/admin/verifications/{submitted.data['id']}/action/",
        {"action": "reject", "reason": "Document is blurry."},
        format="json",
    )
    mine = buyer_client.get(VERIFICATION)

    assert mine.status_code == 200
    assert mine.data[0]["status"] == "REJECTED"
    assert mine.data[0]["rejection_reason"] == "Document is blurry."

    resubmitted = buyer_client.post(VERIFICATION, {"document_image_id": image.pk}, format="json")
    assert resubmitted.status_code == 201
    assert resubmitted.data["status"] == "PENDING"


def test_store_verification_needs_a_store_and_a_business_number(buyer_client, buyer):
    response = buyer_client.post(STORE_VERIFICATION, {"nif_number": "123"}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "store_required"


def test_only_staff_can_open_the_moderation_queue(buyer_client):
    for url in (
        f"{TRUST}/admin/overview/",
        f"{TRUST}/admin/reports/",
        f"{TRUST}/admin/verifications/",
        f"{TRUST}/admin/appeals/",
        f"{TRUST}/admin/blocklist/",
        f"{TRUST}/admin/audit/",
    ):
        assert buyer_client.get(url).status_code == 403, url


# ---------------------------------------------------------------------------
# Blocklists
# ---------------------------------------------------------------------------
def test_blocklist_values_are_normalised():
    assert normalize_value(BlocklistKind.PHONE, "0555 12 34 56") == "+213555123456"
    assert normalize_value(BlocklistKind.BANK_ACCOUNT, "CCP 1234 5678 90") == "1234567890"
    assert normalize_value(BlocklistKind.IMAGE_HASH, "FFAA00") == "ffaa00"


def test_blocklist_matching_ignores_formatting_and_expiry():
    add_entry(kind=BlocklistKind.PHONE, value="+213 555 12 34 56", reason="Banned")

    assert is_blocklisted(BlocklistKind.PHONE, "0555123456")
    assert not is_blocklisted(BlocklistKind.PHONE, "0555999999")

    expired = BlocklistEntry.objects.get()
    expired.expires_at = timezone.now() - timedelta(hours=1)
    expired.save(update_fields=["expires_at"])

    assert not is_blocklisted(BlocklistKind.PHONE, "0555123456")


def test_staff_can_add_and_deactivate_a_blocklist_entry(staff_client):
    created = staff_client.post(
        f"{TRUST}/admin/blocklist/",
        {"kind": "PHONE", "value": "0666777888", "reason": "Scam reports"},
        format="json",
    )

    assert created.status_code == 201
    assert created.data["value"] == "+213666777888"
    entry_id = created.data["id"]

    deactivated = staff_client.delete(f"{TRUST}/admin/blocklist/{entry_id}/")
    assert deactivated.status_code == 204
    assert not is_blocklisted(BlocklistKind.PHONE, "0666777888")


def test_admin_overview_counts_the_queue(staff_client, buyer):
    Report.objects.create(
        reporter=buyer,
        reported_user=UserFactory(),
        reason="SCAM",
        sla_due_at=timezone.now() + timedelta(hours=1),
    )

    response = staff_client.get(f"{TRUST}/admin/overview/")

    assert response.status_code == 200
    assert response.data["open_reports"] == 1
    assert "overdue_reports" in response.data
    assert "pending_verifications" in response.data


# ---------------------------------------------------------------------------
# Reports, SLAs and moderation actions
# ---------------------------------------------------------------------------
def test_report_sla_depends_on_risk(buyer_client, buyer, seller):
    listing = classified(seller)

    for reason in ("SCAM", "HARASSMENT", "SPAM"):
        response = buyer_client.post(
            "/api/v1/messages/reports/",
            {"listing_id": listing.pk, "reason": reason},
            format="json",
        )
        assert response.status_code == 201

    reports = {report.reason: report for report in Report.objects.all()}
    assert reports["SCAM"].sla_due_at < reports["HARASSMENT"].sla_due_at
    assert reports["HARASSMENT"].sla_due_at < reports["SPAM"].sla_due_at
    assert reports["SCAM"].is_overdue is False


def test_an_old_open_report_is_overdue(buyer_client, buyer, seller):
    listing = classified(seller)
    response = buyer_client.post(
        "/api/v1/messages/reports/",
        {"listing_id": listing.pk, "reason": "SCAM"},
        format="json",
    )
    report = Report.objects.get(pk=response.data["id"])
    report.sla_due_at = timezone.now() - timedelta(minutes=1)
    report.save(update_fields=["sla_due_at"])

    queue = buyer_client.get(f"{TRUST}/admin/reports/?overdue=1")

    assert queue.status_code == 403  # buyer cannot read the queue
    staff_queue = APIClient()
    staff_queue.force_authenticate(UserFactory(is_staff=True))
    assert staff_queue.get(f"{TRUST}/admin/reports/?overdue=1").data[0]["is_overdue"] is True


def test_actioning_a_report_removes_the_listing_and_writes_an_audit_row(
    buyer_client, buyer, seller, staff_client
):
    listing = classified(seller)
    created = buyer_client.post(
        "/api/v1/messages/reports/",
        {"listing_id": listing.pk, "reason": "COUNTERFEIT", "details": "Fake"},
        format="json",
    )

    response = staff_client.post(
        f"{TRUST}/admin/reports/{created.data['id']}/action/",
        {"action": "action", "action_taken": "listing_removed", "resolution": "Counterfeit"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == "ACTIONED"
    assert response.data["action_taken"] == "listing_removed"
    listing.refresh_from_db()
    assert listing.status == ListingStatus.ARCHIVED
    assert listing.rejection_reason == "Counterfeit"
    assert ModerationAuditLog.objects.filter(
        action="LISTING_REMOVED", target_id=listing.pk
    ).exists()


def test_banning_a_reported_user_deactivates_and_blocklists_them(
    buyer_client, buyer, seller, staff_client
):
    phone_verified(seller, "+213555111222")
    listing = classified(seller)
    created = buyer_client.post(
        "/api/v1/messages/reports/",
        {"listing_id": listing.pk, "reason": "SCAM"},
        format="json",
    )

    response = staff_client.post(
        f"{TRUST}/admin/reports/{created.data['id']}/action/",
        {"action": "action", "action_taken": "user_banned", "resolution": "Scammer"},
        format="json",
    )

    assert response.status_code == 200
    seller.refresh_from_db()
    assert seller.is_active is False
    assert AccountSanction.objects.filter(user=seller, kind="BAN", is_active=True).exists()
    assert is_blocklisted(BlocklistKind.PHONE, "+213555111222")


def test_a_report_cannot_be_actioned_twice(buyer_client, buyer, seller, staff_client):
    listing = classified(seller)
    created = buyer_client.post(
        "/api/v1/messages/reports/",
        {"listing_id": listing.pk, "reason": "SPAM"},
        format="json",
    )
    staff_client.post(
        f"{TRUST}/admin/reports/{created.data['id']}/action/",
        {"action": "dismiss"},
        format="json",
    )

    second = staff_client.post(
        f"{TRUST}/admin/reports/{created.data['id']}/action/",
        {"action": "dismiss"},
        format="json",
    )

    assert second.status_code == 400
    assert second.data["code"] == "already_reviewed"


def test_mass_ban_by_phone_hits_every_account_and_blocks_the_number(staff_client):
    # Unverified accounts may share a number (the unique constraint only
    # covers verified phones), which is exactly the scammer pattern support
    # needs to sweep in one action.
    first = UserFactory(phone_number="+213555333444")
    second = UserFactory(phone_number="+213555333444")

    response = staff_client.post(
        f"{TRUST}/admin/mass-action/",
        {"identifier": "+213555333444", "action": "ban", "reason": "Serial scammer"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["affected"] == 2
    for user in (first, second):
        user.refresh_from_db()
        assert user.is_active is False
    assert is_blocklisted(BlocklistKind.PHONE, "+213555333444")


def test_reinstating_lifts_the_active_sanction(staff_client, seller):
    seller.is_active = False
    seller.save(update_fields=["is_active"])
    AccountSanction.objects.create(user=seller, kind="BAN", reason="Mistake", is_active=True)

    response = staff_client.post(
        f"{TRUST}/admin/mass-action/",
        {"identifier": str(seller.pk), "action": "reinstate"},
        format="json",
    )

    assert response.status_code == 200
    seller.refresh_from_db()
    assert seller.is_active is True
    assert AccountSanction.objects.filter(user=seller, is_active=False).exists()


def test_ban_evasion_reports_signals_without_auto_banning(staff_client):
    banned = phone_verified(UserFactory(), "+213555777888")
    add_entry(kind=BlocklistKind.PHONE, value="+213555777888", reason="Ban")
    AccountSanction.objects.create(user=banned, kind="BAN", reason="Scam")

    response = staff_client.get(f"{TRUST}/admin/ban-evasion/?user_id={banned.pk}")

    assert response.status_code == 200
    assert response.data["evasion_detected"] is True
    kinds = {signal["kind"] for signal in response.data["signals"]}
    assert "phone_blocklisted" in kinds
    assert "previous_ban" in kinds


# ---------------------------------------------------------------------------
# Appeals
# ---------------------------------------------------------------------------
def test_a_rejected_listing_can_be_appealed_and_restored(buyer_client, buyer, staff_client):
    seller = phone_verified(SellerFactory())
    listing = classified(
        seller, status=ListingStatus.REJECTED, rejection_reason="Prohibited", wilaya=WilayaFactory()
    )
    client = APIClient()
    client.force_authenticate(user=seller)

    created = client.post(
        APPEALS,
        {"kind": "LISTING", "listing_id": listing.pk, "message": "This is a bicycle."},
        format="json",
    )

    assert created.status_code == 201
    assert created.data["status"] == "OPEN"

    approved = staff_client.post(
        f"{TRUST}/admin/appeals/{created.data['id']}/action/",
        {"action": "approve", "resolution": "Reviewed"},
        format="json",
    )

    assert approved.status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.DRAFT
    assert listing.rejection_reason == ""
    assert ModerationAuditLog.objects.filter(action="APPEAL_APPROVED").exists()


def test_you_cannot_appeal_someone_elses_listing(buyer_client, seller):
    listing = classified(seller, status=ListingStatus.REJECTED, wilaya=WilayaFactory())

    response = buyer_client.post(
        APPEALS,
        {"kind": "LISTING", "listing_id": listing.pk, "message": "Mine now"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "invalid_appeal_target"


def test_only_a_rejected_or_archived_listing_is_appealable(seller_client, seller):
    listing = classified(seller, status=ListingStatus.ACTIVE, wilaya=WilayaFactory())

    response = seller_client.post(
        APPEALS,
        {"kind": "LISTING", "listing_id": listing.pk, "message": "Please"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "appeal_not_available"


def test_only_one_open_appeal_per_target(buyer_client, seller):
    listing = classified(seller, status=ListingStatus.REJECTED, wilaya=WilayaFactory())
    client = APIClient()
    client.force_authenticate(user=seller)
    payload = {"kind": "LISTING", "listing_id": listing.pk, "message": "Please"}

    assert client.post(APPEALS, payload, format="json").status_code == 201
    second = client.post(APPEALS, payload, format="json")

    assert second.status_code == 400
    assert second.data["code"] == "appeal_already_open"


def test_approving_a_review_appeal_publishes_the_review(buyer_client, buyer, staff_client, seller):
    listing = classified(seller)
    mine = ProductReviewFactory(
        product=listing, user=buyer, rating=2, comment="Hidden", is_approved=False
    )

    created = buyer_client.post(
        APPEALS,
        {"kind": "REVIEW", "review_id": mine.pk, "message": "It was a real experience."},
        format="json",
    )
    assert created.status_code == 201

    staff_client.post(
        f"{TRUST}/admin/appeals/{created.data['id']}/action/",
        {"action": "approve"},
        format="json",
    )

    mine.refresh_from_db()
    assert mine.is_approved is True
    assert Appeal.objects.get(pk=created.data["id"]).status == "APPROVED"


# ---------------------------------------------------------------------------
# Review moderation and verified purchases
# ---------------------------------------------------------------------------
def test_store_product_reviews_require_a_delivered_order(buyer_client, product):
    response = buyer_client.post(
        "/api/v1/products/reviews/create/",
        {"product": product.pk, "rating": 5, "comment": "Great"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "verified_purchase_required"


def test_a_verified_purchase_is_auto_approved(buyer_client, buyer, product):
    from tests.factories import OrderItemFactory

    OrderItemFactory(order__user=buyer, order__order_status="DELIVERED", product=product)

    response = buyer_client.post(
        "/api/v1/products/reviews/create/",
        {"product": product.pk, "rating": 5, "comment": "Delivered as promised."},
        format="json",
    )

    assert response.status_code == 201, response.data
    review = ProductReview.objects.get(product=product, user=buyer)
    assert review.is_approved is True
    assert review.is_verified_purchase is True


def test_a_new_accounts_classified_review_starts_pending(buyer_client, buyer, seller):
    listing = classified(seller)

    response = buyer_client.post(
        "/api/v1/products/reviews/create/",
        {"product": listing.pk, "rating": 4, "comment": "Seems fine."},
        format="json",
    )

    assert response.status_code == 201, response.data
    review = ProductReview.objects.get(product=listing, user=buyer)
    assert review.is_approved is False
    assert review.is_verified_purchase is False


def test_only_approved_reviews_count_in_the_public_rating(buyer_client, buyer, seller):
    listing = classified(seller)
    ProductReviewFactory(product=listing, user=buyer, rating=5, is_approved=True)
    ProductReviewFactory(product=listing, user=UserFactory(), rating=1, is_approved=False)

    detail = buyer_client.get(f"/api/v1/products/{listing.pk}/")

    assert float(detail.data["average_rating"]) == 5.0
    assert detail.data["review_count"] == 1


def test_the_listing_payload_exposes_the_seller_tier_and_badges(api_client, seller):
    phone_verified(seller)
    SellerVerification.objects.create(user=seller, kind="IDENTITY", status="APPROVED")
    listing = classified(seller)

    detail = api_client.get(f"/api/v1/products/{listing.pk}/")

    assert detail.data["seller"]["tier"] == "ID"
    assert detail.data["seller"]["reputation"]["tier"] == "ID"
    assert "seller_tier" in detail.data
    assert detail.data["seller_badges"][0]["code"] == "ID"
