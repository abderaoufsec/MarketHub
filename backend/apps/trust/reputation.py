"""Seller tiers, badges and the reputation score (Phase 17).

Tiers are *derived* from approved verification rows:

    UNVERIFIED -> PHONE -> ID -> STORE

The reputation score is a small, explainable number (never a black box): the
breakdown is returned to the client so a seller can see what raises it. It is
cached for ``TRUST_REPUTATION_CACHE_SECONDS`` because the detail page asks for
it once per listing, and computing it scans orders, chats and reports.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import SellerVerification, VerificationKind, VerificationStatus

TIER_UNVERIFIED = "UNVERIFIED"
TIER_PHONE = "PHONE"
TIER_ID = "ID"
TIER_STORE = "STORE"

TIER_ORDER = (TIER_UNVERIFIED, TIER_PHONE, TIER_ID, TIER_STORE)

_BADGE_LABELS = {
    TIER_UNVERIFIED: _("Unverified"),
    TIER_PHONE: _("Phone verified"),
    TIER_ID: _("ID verified"),
    TIER_STORE: _("Verified store"),
}


def _approved(user, kind: str) -> bool:
    if user is None:
        return False
    prefetched = getattr(user, "_prefetched_objects_cache", {}).get("trust_verifications")
    rows = prefetched if prefetched is not None else user.trust_verifications.all()
    return any(row.kind == kind and row.status == VerificationStatus.APPROVED for row in rows)


def tier_for_user(user) -> str:
    """The highest badge this user has actually earned."""
    if user is None:
        return TIER_UNVERIFIED
    if _approved(user, VerificationKind.STORE):
        return TIER_STORE
    if _approved(user, VerificationKind.IDENTITY):
        return TIER_ID
    if getattr(user, "phone_verified", False):
        return TIER_PHONE
    return TIER_UNVERIFIED


def tier_label(tier: str) -> str:
    return str(_BADGE_LABELS.get(tier, _BADGE_LABELS[TIER_UNVERIFIED]))


def badges_for_user(user) -> list[dict]:
    """All badges earned so far, most prestigious first.

    A store owner who also verified their identity keeps both rows: the UI
    shows "Verified store" as the primary badge and the rest as supporting
    signals.
    """
    if user is None:
        return [{"code": TIER_UNVERIFIED, "label": tier_label(TIER_UNVERIFIED)}]
    codes: list[str] = []
    if _approved(user, VerificationKind.STORE):
        codes.append(TIER_STORE)
    if _approved(user, VerificationKind.IDENTITY):
        codes.append(TIER_ID)
    if getattr(user, "phone_verified", False):
        codes.append(TIER_PHONE)
    if not codes:
        codes.append(TIER_UNVERIFIED)
    return [{"code": code, "label": tier_label(code)} for code in codes]


def invalidate_reputation(user_id: int) -> None:
    cache.delete(f"trust:reputation:{user_id}")


def is_verified_purchase(user, product) -> bool:
    """A delivered order line is the only proof that a review is real.

    Store products require this before a review can be accepted; classifieds
    have no order row at all, so their reviews rely on the trust score.
    """
    if user is None or product is None:
        return False
    from apps.orders.models import OrderItem

    return OrderItem.objects.filter(
        order__user=user,
        product=product,
        order__order_status="DELIVERED",
    ).exists()


def compute_reputation(user, *, use_cache: bool = True) -> dict:
    """The seller reputation payload, with a transparent component breakdown."""
    if user is None:
        return {
            "score": 0,
            "tier": TIER_UNVERIFIED,
            "tier_label": tier_label(TIER_UNVERIFIED),
            "badges": badges_for_user(None),
            "completed_orders": 0,
            "response_rate": 0.0,
            "response_samples": 0,
            "reports_received": 0,
            "account_age_days": 0,
            "breakdown": {},
        }

    key = f"trust:reputation:{user.pk}"
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    from apps.messaging.models import Conversation, Report

    completed_orders = (
        user.listings.filter(orderitem__order__order_status="DELIVERED")
        .values("orderitem__order_id")
        .distinct()
        .count()
    )
    conversations = Conversation.objects.filter(seller=user)
    total_conversations = conversations.count()
    answered = (
        conversations.filter(
            messages__sender_id=user.pk,
        )
        .distinct()
        .count()
    )
    response_rate = round(answered / total_conversations, 3) if total_conversations else 0.0
    response_samples = total_conversations

    since = timezone.now() - timedelta(days=90)
    reports_received = (
        Report.objects.filter(reported_user=user, created_at__gte=since)
        .exclude(status="DISMISSED")
        .count()
    )
    account_age_days = max((timezone.now() - user.date_joined).days, 0)
    tier = tier_for_user(user)

    breakdown = {
        "base": 20,
        "phone_verified": 15 if getattr(user, "phone_verified", False) else 0,
        "identity_verified": 15 if tier in (TIER_ID, TIER_STORE) else 0,
        "store_verified": 10 if tier == TIER_STORE else 0,
        "completed_orders": min(completed_orders, 10) * 2,
        "response_rate": round(response_rate * 15),
        "account_age": round(min(account_age_days, 180) / 180 * 10),
        "reports_penalty": -min(reports_received * 5, 30),
    }
    score = max(0, min(100, sum(breakdown.values())))

    payload = {
        "score": score,
        "tier": tier,
        "tier_label": tier_label(tier),
        "badges": badges_for_user(user),
        "completed_orders": completed_orders,
        "response_rate": response_rate,
        "response_samples": response_samples,
        "reports_received": reports_received,
        "account_age_days": account_age_days,
        "breakdown": breakdown,
    }
    if use_cache:
        cache.set(key, payload, settings.TRUST_REPUTATION_CACHE_SECONDS)
    return payload


def review_should_auto_approve(user, product=None) -> bool:
    """Review moderation gate.

    A verified purchase is enough on its own. Otherwise the author must look
    like a real, established account: the threshold and minimum age live in
    settings so the policy can be tuned without a deploy of logic.
    """
    if is_verified_purchase(user, product):
        return True
    if user is None:
        return False
    age_days = (timezone.now() - user.date_joined).days
    if age_days < settings.TRUST_REVIEW_MIN_ACCOUNT_AGE_DAYS:
        return False
    score = compute_reputation(user)["score"]
    return score >= settings.TRUST_REVIEW_AUTO_APPROVE_SCORE


def has_approved_identity(user) -> bool:
    return SellerVerification.objects.filter(
        user=user,
        kind=VerificationKind.IDENTITY,
        status=VerificationStatus.APPROVED,
    ).exists()
