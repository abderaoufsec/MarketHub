"""Instant saved-search alerts on publish (Phase 15).

A ``post_save`` signal is the only hook that catches *every* way a listing
becomes visible - the wizard's lifecycle action, the admin, a future bulk
importer - without asking each caller to remember alerts. The transition (not
just "status is ACTIVE") is what matters: editing a live listing must not
re-notify everyone watching the category.

The previous status is read in ``pre_save`` because ``post_save`` only sees
the new row. Sending is synchronous and best-effort (``alerts.notify_instant``
logs failures); Phase 22 replaces it with a queued task without changing this
contract.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.products.models import ListingStatus, Product

logger = logging.getLogger("apps.search.signals")


@receiver(pre_save, sender=Product)
def remember_previous_status(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = (
        sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


@receiver(post_save, sender=Product)
def alert_on_publish(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    became_active = instance.status == ListingStatus.ACTIVE and (
        created or getattr(instance, "_previous_status", None) != ListingStatus.ACTIVE
    )
    if not became_active:
        return
    # Imported here so app loading never pulls the search stack into models.
    from .alerts import notify_instant

    try:
        notify_instant(instance)
    except Exception:
        logger.exception("instant saved-search alerts failed for product %s", instance.pk)
