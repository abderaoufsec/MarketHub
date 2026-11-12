"""Evaluating saved searches and firing alerts (Phase 15).

A saved search is exactly a search URL, so evaluating it is exactly the search
pipeline: ``matching`` for the text, ``apply_search_filters`` for the rest.
No second query language, and an alert can never disagree with the page it
links to.

Two cadences share this module:

* ``notify_instant`` - called after a listing becomes ACTIVE (signals). It
  evaluates every active INSTANT search against that one row and sends on
  each enabled channel. Sellers never get alerts about their own listings.
* ``send_daily_digests`` - the ``send_search_alerts`` management command.
  Each DAILY search gets the listings posted since its last notification (or
  the last 24 h on the first run), capped at five per alert.

Delivery is best-effort by design: the caller is usually a ``post_save``
signal inside a publish request, and a dead SMS gateway must not roll back a
listing.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from apps.products.filters import apply_search_filters
from apps.products.models import Product

from .models import SavedSearch
from .notifications import deliver
from .services import get_search_service

logger = logging.getLogger("apps.search.alerts")

#: One alert never lists the whole catalogue; the link carries the rest.
ALERT_PRODUCT_LIMIT = 5


def _base_queryset(saved_search: SavedSearch) -> QuerySet:
    """Public listings that are not the subscriber's own."""
    return Product.objects.public().exclude(seller=saved_search.user)


def _filtered(saved_search: SavedSearch, queryset: QuerySet) -> QuerySet:
    params = saved_search.params or {}
    service = get_search_service()
    if params.get("q"):
        queryset = service.matching(queryset, params["q"])
    return apply_search_filters(queryset, params)


def matches_product(saved_search: SavedSearch, product: Product) -> bool:
    """Whether one listing matches a saved search (own listings excluded)."""
    return _filtered(saved_search, _base_queryset(saved_search).filter(pk=product.pk)).exists()


def instant_subscribers():
    """Active INSTANT searches that have at least one enabled channel."""
    return SavedSearch.objects.filter(
        is_active=True,
        frequency=SavedSearch.Frequency.INSTANT,
        user__is_active=True,
    ).select_related("user")


def notify_instant(product: Product) -> int:
    """Send an alert to every matching INSTANT search; return the count.

    A listing only reaches this function once (the signal tracks the
    ACTIVE transition), so there is no per-alert dedupe table. The seller's
    own saved searches are excluded in ``_base_queryset``.
    """
    if not getattr(settings, "SEARCH_INSTANT_ALERTS", True):
        return 0
    sent = 0
    for saved_search in instant_subscribers():
        if not saved_search.has_channel:
            continue
        if not matches_product(saved_search, product):
            continue
        try:
            deliver(saved_search, [product])
        except Exception:
            logger.exception("instant alert %s failed", saved_search.pk)
            continue
        SavedSearch.objects.filter(pk=saved_search.pk).update(last_notified_at=timezone.now())
        sent += 1
    return sent


def send_daily_digests(now=None, dry_run: bool = False, limit: int | None = None) -> dict:
    """Run every due DAILY saved search; return a small report.

    ``limit`` caps the number of saved searches processed (a smoke run on a
    production-sized table). ``dry_run`` evaluates and reports without sending
    or touching ``last_notified_at``.
    """
    now = now or timezone.now()
    queryset = SavedSearch.objects.filter(
        is_active=True,
        frequency=SavedSearch.Frequency.DAILY,
        user__is_active=True,
    ).select_related("user")
    queryset = queryset.order_by("pk")
    if limit:
        queryset = queryset[:limit]

    report = {"searched": 0, "with_matches": 0, "sent": 0, "failed": 0}
    for saved_search in queryset:
        report["searched"] += 1
        since = saved_search.last_notified_at or (now - timedelta(hours=24))
        matches = list(
            _filtered(
                saved_search, _base_queryset(saved_search).filter(created_at__gt=since)
            ).order_by("-created_at")[:ALERT_PRODUCT_LIMIT]
        )
        if not matches:
            continue
        report["with_matches"] += 1
        if dry_run:
            continue
        try:
            deliver(saved_search, matches)
        except Exception:
            report["failed"] += 1
            logger.exception("daily alert %s failed", saved_search.pk)
            continue
        SavedSearch.objects.filter(pk=saved_search.pk).update(last_notified_at=now)
        report["sent"] += 1
    return report
