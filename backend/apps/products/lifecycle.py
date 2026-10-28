"""Ad lifecycle: the one place a listing's status may change (Phase 13).

    DRAFT → PENDING_REVIEW → ACTIVE → EXPIRED / SOLD / REJECTED / ARCHIVED

Side effects live with the transitions, not with the view that happened to
trigger them:

* ``publish`` stamps ``published_at``/``expires_at``, generates the slug,
  runs the *full* attribute validation and the duplicate/quota gates — the
  draft path deliberately skips those so autosave can never be blocked;
* ``expire`` flips lazily on read (a detail view showing an "active" listing
  that expired last night is a lie the job schedule cannot fix on time) and
  in bulk through ``manage.py expire_listings``;
* anything else raises :class:`ListingLifecycleError` before touching the row,
  so an illegal transition can never half-apply its side effects.

The wizard is the only caller for now; Phase 17 adds the moderation queue
(``LISTINGS_REQUIRE_MODERATION`` already routes ``publish`` through
``PENDING_REVIEW``), and the admin may call the same service.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from core.exceptions import ApiError

from .models import ListingStatus, ListingType, PriceMode

MAX_SLUG_LENGTH = 230  # leaves room for "-<id>" in the canonical URL


class ListingLifecycleError(ApiError):
    """The requested transition does not exist from this status."""

    code = "invalid_transition"
    status_code = 400


#: Allowed transitions. Anything not listed here is a bug or an attack.
TRANSITIONS = {
    ListingStatus.DRAFT: {ListingStatus.PENDING_REVIEW, ListingStatus.ARCHIVED},
    ListingStatus.PENDING_REVIEW: {
        ListingStatus.ACTIVE,
        ListingStatus.REJECTED,
        ListingStatus.DRAFT,
        ListingStatus.ARCHIVED,
    },
    ListingStatus.ACTIVE: {ListingStatus.SOLD, ListingStatus.EXPIRED, ListingStatus.ARCHIVED},
    ListingStatus.EXPIRED: {ListingStatus.ACTIVE, ListingStatus.ARCHIVED},  # renew
    ListingStatus.SOLD: {ListingStatus.ACTIVE, ListingStatus.ARCHIVED},  # relist
    ListingStatus.REJECTED: {
        ListingStatus.DRAFT,
        ListingStatus.PENDING_REVIEW,
        ListingStatus.ARCHIVED,
    },
    ListingStatus.ARCHIVED: {ListingStatus.DRAFT},  # unarchive
}

#: action → (source status or None = "any of TRANSITIONS keys", target, side effect fn name)
ACTIONS = {
    "publish": (None, ListingStatus.PENDING_REVIEW, "_apply_publish"),
    "approve": (ListingStatus.PENDING_REVIEW, ListingStatus.ACTIVE, None),
    "reject": (ListingStatus.PENDING_REVIEW, ListingStatus.REJECTED, None),
    "withdraw": (ListingStatus.PENDING_REVIEW, ListingStatus.DRAFT, None),
    "mark_sold": (ListingStatus.ACTIVE, ListingStatus.SOLD, "_apply_sold"),
    "relist": (ListingStatus.SOLD, ListingStatus.ACTIVE, "_apply_activate"),
    "renew": (ListingStatus.EXPIRED, ListingStatus.ACTIVE, "_apply_activate"),
    "archive": (None, ListingStatus.ARCHIVED, None),
    "unarchive": (ListingStatus.ARCHIVED, ListingStatus.DRAFT, None),
    "expire": (ListingStatus.ACTIVE, ListingStatus.EXPIRED, None),
}


def _valid_until():
    return timezone.now() + timedelta(days=settings.LISTING_VALID_DAYS)


def _set_slug(product):
    """(Re)generate the SEO slug from the current name.

    Kept stable by carrying an existing slug while the name is unchanged;
    a rename while published regenerates it, and old links keep resolving
    by id — the page redirects to whatever the API now calls canonical.
    """
    base = slugify(product.name)[:MAX_SLUG_LENGTH].strip("-") or "listing"
    if product.slug != base:
        product.slug = base


def incomplete_fields(product) -> list:
    """What still blocks publishing, as serializer field names.

    Drives the ``incomplete_listing`` error the wizard renders as a jump to
    the offending step. Deliberately a plain list of names: the client owns
    the copy (i18n), the server owns the rule.
    """
    missing = []
    if not (product.name or "").strip():
        missing.append("name")
    if not (product.description or "").strip():
        missing.append("description")
    if product.category_id is None:
        missing.append("category")
    if product.wilaya_id is None:
        missing.append("wilaya")
    if product.price_mode in (PriceMode.FIXED, PriceMode.NEGOTIABLE) and product.base_price <= 0:
        missing.append("base_price")
    if product.listing_type == ListingType.STORE_PRODUCT and product.store_id is None:
        missing.append("store")
    return missing


def _apply_publish(product, *, allow_duplicate: bool = False):
    """Pre-transition gate for DRAFT/REJECTED → PENDING_REVIEW.

    ``allow_duplicate`` skips only the similarity gate — the seller has seen
    the warning and confirmed ("publish anyway"). Completeness and quota are
    never bypassable: they are limits, not suggestions.
    """
    from apps.catalog.validation import validate_attributes
    from apps.users.plans import can_create_listing, count_active_listings, get_listing_quota

    from .duplicates import find_possible_duplicate

    if product.status not in (ListingStatus.DRAFT, ListingStatus.REJECTED):
        raise ListingLifecycleError(
            "Only a draft can be published.", details={"status": product.status}
        )

    missing = incomplete_fields(product)
    if missing:
        raise ApiError(
            "The listing is not ready to publish.",
            code="incomplete_listing",
            status_code=400,
            details={"missing": missing},
        )

    # Full attribute validation — the draft path stores whatever it has, the
    # publish path is where "required" actually means required.
    try:
        validate_attributes(product.category, product.attributes_json or {})
    except Exception as exc:  # django ValidationError from the validator
        raise ApiError(
            "Some attributes are invalid.",
            code="invalid_attributes",
            status_code=400,
            details={"errors": [str(m) for m in getattr(exc, "messages", [str(exc)])]},
        ) from exc

    # Quota: only count what publishing would add — a REJECTED relaunch does
    # not occupy a slot (rejected rows are not in the ACTIVE count).
    if not can_create_listing(product.seller):
        raise ApiError(
            "Active listing quota reached.",
            code="quota_reached",
            status_code=400,
            details={
                "quota": get_listing_quota(product.seller),
                "active": count_active_listings(product.seller),
            },
        )

    duplicate = None
    if not allow_duplicate:
        duplicate = find_possible_duplicate(
            product.seller,
            name=product.name,
            category_id=product.category_id,
            base_price=product.base_price,
            price_mode=product.price_mode,
            instance_id=product.pk,
            # Same *kind* of offer: a classified titled like the seller's
            # store SKU is not a repost of it, and variants are legitimate
            # inside a catalogue.
            listing_type=product.listing_type,
        )
    if duplicate is not None:
        raise ApiError(
            "You already have a very similar listing.",
            code="possible_duplicate",
            status_code=400,
            details={
                "duplicate_of": duplicate.pk,
                "duplicate_name": duplicate.name,
                "duplicate_status": duplicate.status,
            },
        )

    product.published_at = product.published_at or timezone.now()
    product.expires_at = _valid_until()
    _set_slug(product)


def _apply_sold(product):
    product.sold_at = timezone.now()


def _apply_activate(product):
    """renew/relist: give a fresh window and take the listing live again."""
    product.expires_at = _valid_until()
    product.sold_at = None
    _set_slug(product)


def transition(product, action: str, *, allow_duplicate: bool = False):
    """Run ``action`` on ``product``; return the saved instance.

    The single entry point for every status change. Validates the edge,
    applies the side effect, saves with an explicit ``update_fields`` so an
    ``auto_now`` timestamp does not silently rewrite unrelated columns.

    ``allow_duplicate`` is only ever read by ``publish``: it carries the
    seller's "yes, I know it looks like my other ad" confirmation past the
    similarity gate. It is ignored by every other action rather than rejected,
    so a client retrying a stale payload cannot get a confusing error.
    """
    spec = ACTIONS.get(action)
    if spec is None:
        raise ListingLifecycleError(
            f"Unknown action {action!r}.", details={"allowed": sorted(ACTIONS)}
        )
    source, target, effect = spec

    allowed = TRANSITIONS.get(product.status, set())
    if target not in allowed or (source is not None and product.status != source):
        raise ListingLifecycleError(
            f"Cannot {action} a listing in status {product.status}.",
            details={"status": product.status, "action": action},
        )

    with transaction.atomic():
        # Side effects first: they may raise (incomplete, quota, duplicate),
        # and the row must be untouched when they do.
        _apply(product, effect, allow_duplicate=allow_duplicate)
        product.status = target
        product.save(
            update_fields=["status", "updated_at", "published_at", "expires_at", "sold_at", "slug"]
        )

    return product


def _apply(product, effect, *, allow_duplicate: bool = False):
    if effect == "_apply_publish":
        _apply_publish(product, allow_duplicate=allow_duplicate)
    elif effect == "_apply_sold":
        _apply_sold(product)
    elif effect == "_apply_activate":
        _apply_activate(product)


def publish(product, *, allow_duplicate: bool = False):
    """DRAFT/REJECTED → (PENDING_REVIEW →) ACTIVE.

    With moderation off — today's default — the listing walks the full
    ``PENDING_REVIEW`` edge and is approved in the same transaction, so the
    state machine is exercised exactly once and Phase 17 flips a *setting*
    rather than a code path.
    """
    product = transition(product, "publish", allow_duplicate=allow_duplicate)
    if not settings.LISTINGS_REQUIRE_MODERATION:
        product = transition(product, "approve")
    return product


def expire_if_due(product):
    """Lazily flip a listing whose window closed. Idempotent, no-op otherwise.

    Called from the public detail view: without a running beat (Phase 22) a
    listing must not render as ACTIVE the morning after it expired, and with
    one this is just the belt to the job's braces.
    """
    if product.status == ListingStatus.ACTIVE and product.is_expired:
        return transition(product, "expire")
    return product
