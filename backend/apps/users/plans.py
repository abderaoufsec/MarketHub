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
