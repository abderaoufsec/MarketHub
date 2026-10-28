"""
Seller plan quotas — stub introduced in Phase 2 of docs/todo.md.

Every seller is currently on the *free* plan and gets
``settings.MAX_PRODUCTS_PER_SELLER`` listings. Real plans (Free / Pro /
Business) with billing, per-plan quotas and feature flags land in Phase 21;
this module is the single choke point, so Phase 21 only has to change how
plans are resolved and what the quotas are.

Quota semantics: an ``int`` caps the number of listings, ``None`` means
unlimited.
"""

from __future__ import annotations

from django.conf import settings

FREE = "free"
PRO = "pro"
BUSINESS = "business"

PLAN_CHOICES = (
    (FREE, "Free"),
    (PRO, "Pro"),
    (BUSINESS, "Business"),
)

# Listing quota per plan. ``None`` means unlimited. The free value comes from
# settings (env-tunable) and is read on every call, so operators can change it
# without a deploy.
PLAN_PRODUCT_QUOTAS = {
    PRO: 500,
    BUSINESS: None,  # unlimited
}


def get_plan(user) -> str:
    """Return the plan code for a user.

    Phase 21 replaces the attribute lookup with a real plan/billing record;
    everything else in the codebase already goes through this function.
    """
    if user is None:
        return FREE
    plan = getattr(user, "plan", FREE)
    return plan or FREE


def get_product_quota(user) -> int | None:
    """Max number of products the user may create, or ``None`` for unlimited."""
    plan = get_plan(user)
    if plan == FREE:
        return settings.MAX_PRODUCTS_PER_SELLER
    return PLAN_PRODUCT_QUOTAS.get(plan, settings.MAX_PRODUCTS_PER_SELLER)


def can_create_product(user, current_count: int) -> bool:
    """Whether ``user`` may create one more product given ``current_count``."""
    quota = get_product_quota(user)
    return quota is None or current_count < quota


# ---------------------------------------------------------------------------
# Phase 13: per-user active-listing quotas (free / verified / store plan).
#
# Unit is the *seller's* ACTIVE listings of any type — a classified counts
# the same as a store SKU. Enforced when the wizard publishes, not when a
# draft is saved (an autosave that hits a quota line is a lost seller), and
# read by /products/seller/quota/ for the dashboard and the wizard's header.
#
# A seller who owns a store is never capped below the legacy
# ``MAX_PRODUCTS_PER_SELLER`` tier, so activating a store can only raise the
# ceiling — the two caps are monotonic instead of fighting each other.
# Phase 21 replaces the tier arithmetic with billing; the seam is unchanged.
# ---------------------------------------------------------------------------

#: Paid plans. ``None`` = unlimited; the free tier comes from settings.
LISTING_QUOTAS = {
    PRO: 500,
    BUSINESS: None,
}

#: Phone-verified users post more: the free tier times this.
VERIFIED_MULTIPLIER = 3


def get_listing_quota(user) -> int | None:
    """Max ACTIVE listings the user may keep live, ``None`` for unlimited."""
    plan = get_plan(user)
    if plan in LISTING_QUOTAS:
        return LISTING_QUOTAS[plan]

    quota = settings.MAX_ACTIVE_LISTINGS_PER_USER
    if user is not None and getattr(user, "phone_verified", False):
        quota *= VERIFIED_MULTIPLIER
    if user is not None and getattr(user, "store", None) is not None:
        quota = max(quota, settings.MAX_PRODUCTS_PER_SELLER)
    return quota


def count_active_listings(user) -> int:
    """How many live listings the seller currently has.

    Imported late: apps.products.serializers imports this module, so a
    module-level import would close the circle.
    """
    from apps.products.models import ListingStatus, Product

    if user is None or not getattr(user, "pk", None):
        return 0
    return Product.objects.filter(seller=user, status=ListingStatus.ACTIVE).count()


def can_create_listing(user) -> bool:
    """Whether publishing one more listing fits the user's tier."""
    quota = get_listing_quota(user)
    return quota is None or count_active_listings(user) < quota


def max_draft_listings() -> int:
    """Drafts are free but bounded — they are rows, not invitations."""
    return settings.MAX_DRAFT_LISTINGS
