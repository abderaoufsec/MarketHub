"""Trust & safety service layer (Phase 17).

Views stay thin and models stay dumb: every state change that needs an audit
row, a cache invalidation or a second table goes through here.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.products import lifecycle
from apps.products.models import ListingStatus, Product, ProductReview
from core.exceptions import ApiError

from .blocklists import add_entry, is_blocklisted
from .models import (
    AccountSanction,
    Appeal,
    AppealKind,
    AppealStatus,
    AuditAction,
    BlocklistKind,
    ModerationAuditLog,
    SanctionKind,
    SellerVerification,
    VerificationKind,
    VerificationStatus,
)
from .reputation import invalidate_reputation

User = get_user_model()


def record_audit(
    *,
    actor,
    action: str,
    target_type: str = "",
    target_id: int | None = None,
    reason: str = "",
    metadata: dict | None = None,
) -> ModerationAuditLog:
    return ModerationAuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason or "",
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Seller verification
# ---------------------------------------------------------------------------
def submit_identity_verification(user, validated_data: dict) -> SellerVerification:
    if not getattr(user, "phone_verified", False):
        raise ApiError(
            "Verify your phone number before submitting an ID.",
            code="phone_verification_required",
        )
    with transaction.atomic():
        verification, _ = SellerVerification.objects.update_or_create(
            user=user,
            kind=VerificationKind.IDENTITY,
            defaults={
                "status": VerificationStatus.PENDING,
                "document_image": validated_data.get("document_image"),
                "selfie_image": validated_data.get("selfie_image"),
                "document_type": validated_data.get("document_type", ""),
                "document_number": validated_data.get("document_number", ""),
                "store": None,
                "rejection_reason": "",
                "reviewed_at": None,
                "reviewed_by": None,
                "metadata": validated_data.get("metadata", {}),
            },
        )
        record_audit(
            actor=user,
            action=AuditAction.VERIFICATION_SUBMITTED,
            target_type="verification",
            target_id=verification.pk,
            metadata={"kind": verification.kind},
        )
    invalidate_reputation(user.pk)
    return verification


def submit_store_verification(user, validated_data: dict) -> SellerVerification:
    store = getattr(user, "store", None)
    if store is None:
        raise ApiError(
            "Create your store before requesting store verification.", code="store_required"
        )
    if not (validated_data.get("commercial_register_number") or validated_data.get("nif_number")):
        raise ApiError(
            "Provide a commercial register number or a NIF.",
            code="business_document_required",
        )
    with transaction.atomic():
        verification, _ = SellerVerification.objects.update_or_create(
            user=user,
            kind=VerificationKind.STORE,
            defaults={
                "status": VerificationStatus.PENDING,
                "document_image": validated_data.get("document_image"),
                "document_type": validated_data.get("document_type", "COMMERCIAL_REGISTER"),
                "commercial_register_number": validated_data.get("commercial_register_number", ""),
                "nif_number": validated_data.get("nif_number", ""),
                "store": store,
                "rejection_reason": "",
                "reviewed_at": None,
                "reviewed_by": None,
                "metadata": validated_data.get("metadata", {}),
            },
        )
        record_audit(
            actor=user,
            action=AuditAction.VERIFICATION_SUBMITTED,
            target_type="verification",
            target_id=verification.pk,
            metadata={"kind": verification.kind, "store_id": store.pk},
        )
    invalidate_reputation(user.pk)
    return verification


def review_verification(
    verification: SellerVerification,
    *,
    actor,
    approve: bool,
    reason: str = "",
) -> SellerVerification:
    if verification.status != VerificationStatus.PENDING:
        raise ApiError(
            "This verification was already reviewed.",
            code="already_reviewed",
            details={"status": verification.status},
        )
    with transaction.atomic():
        verification.status = (
            VerificationStatus.APPROVED if approve else VerificationStatus.REJECTED
        )
        verification.reviewed_at = timezone.now()
        verification.reviewed_by = actor
        verification.rejection_reason = "" if approve else (reason or "")
        verification.save(
            update_fields=[
                "status",
                "reviewed_at",
                "reviewed_by",
                "rejection_reason",
                "updated_at",
            ]
        )
        record_audit(
            actor=actor,
            action=(
                AuditAction.VERIFICATION_APPROVED if approve else AuditAction.VERIFICATION_REJECTED
            ),
            target_type="verification",
            target_id=verification.pk,
            reason=reason,
            metadata={"kind": verification.kind, "user_id": verification.user_id},
        )
    invalidate_reputation(verification.user_id)
    return verification


# ---------------------------------------------------------------------------
# Reports, removals and sanctions
# ---------------------------------------------------------------------------
def _remove_listing(listing: Product, *, actor, reason: str) -> None:
    if listing.status == ListingStatus.PENDING_REVIEW:
        lifecycle.transition(listing, "reject")
    elif listing.status == ListingStatus.ACTIVE:
        lifecycle.transition(listing, "archive")
    else:
        Product.objects.filter(pk=listing.pk).update(status=ListingStatus.ARCHIVED)
    Product.objects.filter(pk=listing.pk).update(
        rejection_reason=reason or "",
        moderated_at=timezone.now(),
        moderated_by=actor,
    )
    record_audit(
        actor=actor,
        action=AuditAction.LISTING_REMOVED,
        target_type="listing",
        target_id=listing.pk,
        reason=reason,
    )


def apply_sanction(
    user,
    *,
    kind: str,
    actor,
    reason: str = "",
    expires_at=None,
    block_phone: bool = True,
) -> AccountSanction:
    if kind not in SanctionKind.values:
        raise ApiError("Unknown sanction.", code="bad_request")
    with transaction.atomic():
        sanction = AccountSanction.objects.create(
            user=user,
            kind=kind,
            reason=reason or "",
            expires_at=expires_at,
            created_by=actor,
        )
        if kind in (SanctionKind.BAN, SanctionKind.SUSPEND):
            User.objects.filter(pk=user.pk).update(is_active=False)
        if kind == SanctionKind.BAN and block_phone and user.phone_number:
            add_entry(
                kind=BlocklistKind.PHONE,
                value=user.phone_number,
                reason=reason or f"Banned user {user.pk}",
                created_by=actor,
                metadata={"user_id": user.pk, "sanction_id": sanction.pk},
            )
        record_audit(
            actor=actor,
            action=(
                AuditAction.USER_BANNED if kind == SanctionKind.BAN else AuditAction.USER_SUSPENDED
            ),
            target_type="user",
            target_id=user.pk,
            reason=reason,
            metadata={"kind": kind, "sanction_id": sanction.pk},
        )
    invalidate_reputation(user.pk)
    return sanction


def reinstate_user(user, *, actor, reason: str = "") -> None:
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(is_active=True)
        AccountSanction.objects.filter(user=user, is_active=True).update(
            is_active=False, lifted_at=timezone.now()
        )
        record_audit(
            actor=actor,
            action=AuditAction.USER_REINSTATED,
            target_type="user",
            target_id=user.pk,
            reason=reason,
        )
    invalidate_reputation(user.pk)


def review_report(
    report,
    *,
    actor,
    action: str,
    resolution: str = "",
    action_taken: str = "",
) -> object:
    """Move one report to its terminal state, optionally acting on the target.

    ``action`` is ``review`` (no violation), ``dismiss`` (no action) or
    ``action`` (violation confirmed). The concrete consequences are expressed
    in ``action_taken`` so the audit row can say "listing_removed" or
    "user_banned" without guessing from the status.
    """
    if action not in {"review", "dismiss", "action"}:
        raise ApiError("Unknown moderation action.", code="bad_request")
    if report.status != "OPEN":
        raise ApiError(
            "This report was already handled.",
            code="already_reviewed",
            details={"status": report.status},
        )

    with transaction.atomic():
        if action == "action":
            if action_taken == "listing_removed" and report.listing_id:
                _remove_listing(report.listing, actor=actor, reason=resolution)
            elif action_taken == "user_banned":
                apply_sanction(
                    report.reported_user,
                    kind=SanctionKind.BAN,
                    actor=actor,
                    reason=resolution or f"Report {report.pk}",
                )
            elif action_taken == "user_suspended":
                apply_sanction(
                    report.reported_user,
                    kind=SanctionKind.SUSPEND,
                    actor=actor,
                    reason=resolution or f"Report {report.pk}",
                )
            report.status = "ACTIONED"
        elif action == "dismiss":
            report.status = "DISMISSED"
        else:
            report.status = "REVIEWED"

        report.reviewed_at = timezone.now()
        report.reviewed_by = actor
        report.resolution = resolution or ""
        report.action_taken = action_taken or ""
        report.resolved_at = timezone.now()
        report.save(
            update_fields=[
                "status",
                "reviewed_at",
                "reviewed_by",
                "resolution",
                "action_taken",
                "resolved_at",
            ]
        )
        audit_action = {
            "review": AuditAction.REPORT_REVIEWED,
            "dismiss": AuditAction.REPORT_DISMISSED,
            "action": AuditAction.REPORT_ACTIONED,
        }[action]
        record_audit(
            actor=actor,
            action=audit_action,
            target_type="report",
            target_id=report.pk,
            reason=resolution,
            metadata={
                "report_action": action,
                "action_taken": action_taken,
                "reported_user_id": report.reported_user_id,
                "listing_id": report.listing_id,
            },
        )
    return report


def mass_action(identifier: str, *, action: str, actor, reason: str = "") -> dict:
    """Apply a sanction to every account matching a phone number or user id.

    A scammer with several accounts usually shares the phone or re-registers
    with it; support should not have to repeat the same ban five times.
    """
    if action not in {"ban", "suspend", "warn", "reinstate"}:
        raise ApiError("Unknown mass action.", code="bad_request")

    users = User.objects.none()
    phone = None
    if identifier and identifier.isdigit():
        users = User.objects.filter(pk=int(identifier))
    if not users.exists():
        phone = identifier
        users = User.objects.filter(phone_number=identifier)
    users = list(users)

    results = []
    for user in users:
        if action == "reinstate":
            reinstate_user(user, actor=actor, reason=reason)
        else:
            kind = {
                "ban": SanctionKind.BAN,
                "suspend": SanctionKind.SUSPEND,
                "warn": SanctionKind.WARNING,
            }[action]
            apply_sanction(user, kind=kind, actor=actor, reason=reason)
        results.append({"user_id": user.pk, "action": action})

    if action == "ban" and phone:
        add_entry(
            kind=BlocklistKind.PHONE,
            value=phone,
            reason=reason or "Mass ban",
            created_by=actor,
            metadata={"mass_action": True},
        )

    record_audit(
        actor=actor,
        action=AuditAction.MASS_ACTION,
        target_type="user",
        target_id=users[0].pk if len(users) == 1 else None,
        reason=reason,
        metadata={
            "identifier": identifier,
            "action": action,
            "affected": len(users),
            "user_ids": [user.pk for user in users],
        },
    )
    return {
        "action": action,
        "identifier": identifier,
        "affected": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Appeals
# ---------------------------------------------------------------------------
def create_appeal(
    user,
    *,
    kind: str,
    message: str,
    listing: Product | None = None,
    review: ProductReview | None = None,
) -> Appeal:
    if kind not in AppealKind.values:
        raise ApiError("Unknown appeal type.", code="bad_request")
    if not (message or "").strip():
        raise ApiError(
            "Explain why this decision should be reviewed.", code="appeal_message_required"
        )

    if kind == AppealKind.LISTING:
        if listing is None or listing.seller_id != user.pk:
            raise ApiError("That listing is not yours.", code="invalid_appeal_target")
        if listing.status not in (ListingStatus.REJECTED, ListingStatus.ARCHIVED):
            raise ApiError(
                "Only a rejected or archived listing can be appealed.",
                code="appeal_not_available",
                details={"status": listing.status},
            )
    elif kind == AppealKind.REVIEW:
        if review is None or review.user_id != user.pk:
            raise ApiError("That review is not yours.", code="invalid_appeal_target")
        if review.is_approved:
            raise ApiError("That review is already visible.", code="appeal_not_available")
    elif kind == AppealKind.ACCOUNT:
        active = AccountSanction.objects.filter(
            user=user,
            is_active=True,
            kind__in=[SanctionKind.BAN, SanctionKind.SUSPEND],
        ).exists()
        if user.is_active and not active:
            raise ApiError("This account is not restricted.", code="appeal_not_available")

    open_exists = Appeal.objects.filter(
        user=user,
        kind=kind,
        listing=listing,
        review=review,
        status=AppealStatus.OPEN,
    ).exists()
    if open_exists:
        raise ApiError("You already have an open appeal for this.", code="appeal_already_open")

    return Appeal.objects.create(
        user=user,
        kind=kind,
        listing=listing,
        review=review,
        message=message.strip(),
    )


def review_appeal(appeal: Appeal, *, actor, approve: bool, resolution: str = "") -> Appeal:
    if appeal.status != AppealStatus.OPEN:
        raise ApiError(
            "This appeal was already reviewed.",
            code="already_reviewed",
            details={"status": appeal.status},
        )
    with transaction.atomic():
        if approve:
            if appeal.kind == AppealKind.LISTING and appeal.listing_id:
                listing = appeal.listing
                if listing.status == ListingStatus.REJECTED:
                    lifecycle.transition(listing, "restore")
                elif listing.status == ListingStatus.ARCHIVED:
                    lifecycle.transition(listing, "unarchive")
                Product.objects.filter(pk=listing.pk).update(
                    rejection_reason="",
                    moderated_at=timezone.now(),
                    moderated_by=actor,
                )
            elif appeal.kind == AppealKind.ACCOUNT:
                reinstate_user(appeal.user, actor=actor, reason=resolution or "Appeal approved")
            elif appeal.kind == AppealKind.REVIEW and appeal.review_id:
                ProductReview.objects.filter(pk=appeal.review_id).update(
                    is_approved=True,
                    moderated_at=timezone.now(),
                    moderation_note=resolution or "Appeal approved",
                )
        appeal.status = AppealStatus.APPROVED if approve else AppealStatus.REJECTED
        appeal.reviewed_by = actor
        appeal.reviewed_at = timezone.now()
        appeal.resolution = resolution or ""
        appeal.save(update_fields=["status", "reviewed_by", "reviewed_at", "resolution"])
        record_audit(
            actor=actor,
            action=(AuditAction.APPEAL_APPROVED if approve else AuditAction.APPEAL_REJECTED),
            target_type="appeal",
            target_id=appeal.pk,
            reason=resolution,
            metadata={"kind": appeal.kind, "user_id": appeal.user_id},
        )
    invalidate_reputation(appeal.user_id)
    return appeal


# ---------------------------------------------------------------------------
# Ban-evasion signals
# ---------------------------------------------------------------------------
def detect_ban_evasion(user, request=None) -> dict:
    """Evidence that an account is a banned user's next identity.

    Nothing here auto-bans: it is a support-side signal list, because a
    shared family phone or a café IP is not proof.
    """
    signals: list[dict] = []
    if user.phone_number and is_blocklisted(BlocklistKind.PHONE, user.phone_number):
        signals.append({"kind": "phone_blocklisted", "value": user.phone_number})

    request_ip = None
    device = ""
    if request is not None:
        request_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR")
        device = (request.headers.get("X-Device-ID") or "").strip()
    if request_ip and is_blocklisted(BlocklistKind.IP, request_ip):
        signals.append({"kind": "ip_blocklisted", "value": request_ip})
    if device and is_blocklisted(BlocklistKind.DEVICE, device):
        signals.append({"kind": "device_blocklisted", "value": device})

    if user.phone_number:
        same_phone = list(
            User.objects.filter(phone_number=user.phone_number)
            .exclude(pk=user.pk)
            .values_list("pk", flat=True)[:10]
        )
        if same_phone:
            signals.append({"kind": "shared_phone_accounts", "user_ids": same_phone})

    blocked_sanctions = list(
        AccountSanction.objects.filter(kind=SanctionKind.BAN, user=user).values_list(
            "pk", flat=True
        )
    )
    if blocked_sanctions:
        signals.append({"kind": "previous_ban", "sanction_ids": blocked_sanctions})

    return {
        "user_id": user.pk,
        "evasion_detected": bool(signals),
        "signals": signals,
    }
