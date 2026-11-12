"""Seller response-time badge (Phase 16).

The badge answers one question: "if I message this seller, how long do they
usually take?". It is calculated from the first seller reply to the first buyer
message in recent conversations. Two samples is the minimum before showing a
number; a brand-new seller gets no badge rather than a misleading "1 minute".

The result is cached because the listing detail page is public and a seller's
inbox only changes when they send/receive a message (the service invalidates
the key on write).
"""

from __future__ import annotations

from django.core.cache import cache

from .models import Conversation, Message

CACHE_TIMEOUT_SECONDS = 15 * 60
MIN_SAMPLES = 2
MAX_CONVERSATIONS = 200


def cache_key(seller_id: int) -> str:
    return f"messaging:seller-response:{seller_id}"


def invalidate_seller_response_time(seller_id: int) -> None:
    cache.delete(cache_key(seller_id))


def seller_response_time_minutes(seller_id: int | None) -> int | None:
    """Average first-reply time in whole minutes, or ``None`` if too new."""
    if not seller_id:
        return None
    key = cache_key(seller_id)
    cached = cache.get(key, "missing")
    if cached != "missing":
        return cached

    buyers = dict(
        Conversation.objects.filter(seller_id=seller_id)
        .order_by("-last_message_at")
        .values_list("id", "buyer_id")[:MAX_CONVERSATIONS]
    )
    if not buyers:
        cache.set(key, None, CACHE_TIMEOUT_SECONDS)
        return None

    state = {conversation_id: {"first_buyer": None, "reply": None} for conversation_id in buyers}
    rows = (
        Message.objects.filter(conversation_id__in=buyers)
        .order_by("conversation_id", "created_at", "id")
        .values_list("conversation_id", "sender_id", "created_at")
    )
    for conversation_id, sender_id, created_at in rows.iterator():
        item = state[conversation_id]
        if item["reply"] is not None:
            continue
        if sender_id == buyers[conversation_id] and item["first_buyer"] is None:
            item["first_buyer"] = created_at
        elif sender_id == seller_id and item["first_buyer"] is not None:
            item["reply"] = created_at

    seconds = [
        (item["reply"] - item["first_buyer"]).total_seconds()
        for item in state.values()
        if item["first_buyer"] is not None and item["reply"] is not None
    ]
    value = None
    if len(seconds) >= MIN_SAMPLES:
        value = max(1, round((sum(seconds) / len(seconds)) / 60))
    cache.set(key, value, CACHE_TIMEOUT_SECONDS)
    return value
