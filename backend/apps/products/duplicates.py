"""Duplicate-listing detection (Phase 13).

Same seller + similar title + close price → the ad they posted last week.
Runs on **publish**, never on draft autosave: a blocked save while someone is
still typing is a lost seller. Image hashing joins here when Phase 14 lands
(``sha256`` of the bytes today, pHash then); the seam is
:func:`find_possible_duplicate`'s return value, not the caller.

Deliberately extension-free (no pg_trgm — that is Phase 15's dependency): the
candidate set is one seller's recent listings in one category, bounded at 50,
so similarity runs in Python over a handful of rows, not a table scan.
"""

import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher

from django.db.models import Q
from django.utils import timezone

from .models import ListingStatus, PriceMode

#: Title similarity at or above which two names are "the same ad".
TITLE_SIMILARITY = 0.82
#: Relative price proximity counted as the same offer (both ends priced).
PRICE_TOLERANCE = 0.10
#: Only recent listings are duplicates; an old sold ad is history.
RECENT_DAYS = 90
CANDIDATE_LIMIT = 50

_PRICED_MODES = {PriceMode.FIXED, PriceMode.NEGOTIABLE}

_STOPWORDS = {"the", "a", "an", "de", "le", "la", "l", "d", "el", "al"}


def normalize_title(text: str) -> str:
    """Casefold, strip diacritics and punctuation, drop tiny filler words.

    ``"iPhone 13 Pro — neuf !"`` → ``"iphone 13 pro neuf"`` so the French,
    Arabic-transliterated and English spellings of the same ad converge.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    tokens = re.findall(r"\w+", text.casefold())
    return " ".join(t for t in tokens if t not in _STOPWORDS)


def title_similarity(a: str, b: str) -> float:
    """Max of token-set Jaccard and sequence ratio — whichever sees it first.

    Jaccard catches reworded-but-same sets (``"gaming laptop dell"`` vs
    ``"dell gaming laptop"``); the sequence ratio catches one-token edits
    (``"s23 ultra"`` vs ``"s22 ultra"`` still scores high, which is exactly
    what makes it useful *with* the price gate).
    """
    ta, tb = normalize_title(a).split(), normalize_title(b).split()
    if not ta or not tb:
        return 0.0
    jaccard = len(set(ta) & set(tb)) / len(set(ta) | set(tb))
    ratio = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return max(jaccard, ratio)


def price_matches(a_mode, a_price, b_mode, b_price) -> bool:
    """Same offer, tolerance aside. Unpriced modes (on request/free/exchange)
    match each other but never a priced listing."""
    a_priced, b_priced = a_mode in _PRICED_MODES, b_mode in _PRICED_MODES
    if a_priced != b_priced:
        return a_mode == b_mode
    if not a_priced:
        return a_mode == b_mode
    a_price, b_price = float(a_price or 0), float(b_price or 0)
    if a_price == 0 or b_price == 0:
        return a_price == b_price
    return abs(a_price - b_price) <= PRICE_TOLERANCE * max(a_price, b_price)


def find_possible_duplicate(
    seller,
    *,
    name: str,
    category_id,
    base_price,
    price_mode,
    instance_id=None,
    listing_type=None,
):
    """The seller's most recent listing that looks like this one, or ``None``.

    Scans the same seller's recent rows in the same category (all statuses
    that represent an intent to sell — a DRAFT counts: two drafts of the same
    ad is still a duplicate). ``instance_id`` excludes the row being updated.
    """
    if seller is None or not name:
        return None

    from .models import Product

    candidates = (
        Product.objects.filter(
            seller=seller,
            category_id=category_id,
            created_at__gte=timezone.now() - timedelta(days=RECENT_DAYS),
            status__in=(
                ListingStatus.DRAFT,
                ListingStatus.PENDING_REVIEW,
                ListingStatus.ACTIVE,
            ),
        )
        .exclude(pk=instance_id)
        .order_by("-created_at")[:CANDIDATE_LIMIT]
    )

    best, best_score = None, TITLE_SIMILARITY
    for candidate in candidates:
        # Store SKUs sharing a category can legitimately repeat (variants);
        # the spam shape is same seller + same listing_type + same offer.
        if listing_type is not None and candidate.listing_type != listing_type:
            continue
        score = title_similarity(name, candidate.name)
        if score < best_score:
            continue
        if not price_matches(price_mode, base_price, candidate.price_mode, candidate.base_price):
            continue
        best, best_score = candidate, score
    return best


def similar_to(product, limit: int = 8):
    """ "Similar listings" for the detail page (Phase 13).

    Same category (the parent *or a sibling*, so the phone you are looking at
    suggests other phones, not its own subtree only), live, other sellers
    optional but self always excluded; ordered newest-first — without Phase
    15's search index there is no relevance score worth pretending to have.
    """
    from .models import Product

    if product.category_id is None:
        return Product.objects.public().none()

    category = product.category
    # My category and — so a phone suggests *other* phones, not only its own
    # rows — everything filed under the same parent, plus rows sitting on the
    # parent itself. The paths matter: this filter runs on **Product**, so
    # the category's ``parent`` is reached through the FK
    # (``category__parent_id``), never as a Product column.
    roots = Q(category_id=category.pk)
    if category.parent_id:
        roots = (
            roots | Q(category_id=category.parent_id) | Q(category__parent_id=category.parent_id)
        )

    return (
        Product.objects.public()
        .filter(roots)
        .exclude(pk=product.pk)
        .exclude(seller_id=product.seller_id)
        .order_by("-created_at")[:limit]
    )


def more_from_seller(product, limit: int = 8):
    """ "More from this seller": their other live listings, newest first."""
    from .models import Product

    return (
        Product.objects.public()
        .filter(seller_id=product.seller_id)
        .exclude(pk=product.pk)
        .order_by("-created_at")[:limit]
    )
