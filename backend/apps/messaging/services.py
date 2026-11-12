"""Domain services for contact, chat, offers and moderation (Phase 16).

Views stay thin; the invariants live here so a future mobile client or an
admin action cannot bypass them:

* you cannot contact/report/block yourself;
* either side of a block stops all new contact;
* only the two participants can read a conversation;
* a listing's contact mode controls whether a phone may be revealed;
* exactly one offer is pending at a time;
* first messages are checked for phone numbers/links, and repeated identical
  messages are rejected before they become a flood.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.media.models import Image
from apps.products.models import ContactMode, PriceMode, Product
from core.exceptions import ApiError

from .models import (
    Conversation,
    Message,
    MessageKind,
    Offer,
    OfferStatus,
    PhoneReveal,
    Report,
    UserBlock,
)
from .notifications import send_new_message_email
from .spam import first_message_violations, safety_flags
from .stats import invalidate_seller_response_time

logger = logging.getLogger("apps.messaging.services")


def users_blocked(first_id: int, second_id: int) -> bool:
    """True if either user has blocked the other (one direction is enough)."""
    return UserBlock.objects.filter(
        Q(blocker_id=first_id, blocked_id=second_id) | Q(blocker_id=second_id, blocked_id=first_id)
    ).exists()


def _assert_can_contact(conversation, sender) -> None:
    if not conversation.is_participant(sender):
        raise ApiError(
            "You do not have access to this conversation.",
            code="permission_denied",
            status_code=403,
        )
    other = conversation.other_user_for(sender)
    if other is not None and users_blocked(sender.pk, other.pk):
        raise ApiError(
            "You cannot contact this user because one of you blocked the other.",
            code="user_blocked",
            status_code=403,
        )


def get_or_create_conversation(listing_id: int, buyer) -> tuple[Conversation, bool]:
    """Open (or reopen) the single thread between this buyer and this listing."""
    listing = Product.objects.public().select_related("seller").filter(pk=listing_id).first()
    if listing is None:
        raise ApiError(
            "This listing is no longer available.",
            code="product_unavailable",
        )
    if listing.seller_id == buyer.pk:
        raise ApiError(
            "You cannot start a conversation about your own listing.",
            code="cannot_contact_yourself",
        )
    if users_blocked(listing.seller_id, buyer.pk):
        raise ApiError(
            "You cannot contact this user because one of you blocked the other.",
            code="user_blocked",
            status_code=403,
        )

    with transaction.atomic():
        conversation, created = Conversation.objects.get_or_create(
            listing=listing,
            buyer=buyer,
            defaults={"seller": listing.seller},
        )
        # A seller change on the listing (rare, usually a correction) should not
        # leave the thread pointing at the old owner.
        if not created and conversation.seller_id != listing.seller_id:
            conversation.seller = listing.seller
            conversation.save(update_fields=["seller", "updated_at"])
        if not created and conversation.archived_for(buyer):
            field = "buyer_archived" if buyer.pk == conversation.buyer_id else "seller_archived"
            Conversation.objects.filter(pk=conversation.pk).update(**{field: False})
            conversation.refresh_from_db(fields=[field])
    return conversation, created


def _last_message_bump(conversation, sender, now) -> None:
    recipient_archive = (
        "seller_archived" if sender.pk == conversation.buyer_id else "buyer_archived"
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=now,
        updated_at=now,
        **{recipient_archive: False},
    )
    conversation.last_message_at = now
    conversation.updated_at = now
    invalidate_seller_response_time(conversation.seller_id)


def _duplicate_flood(conversation, sender, body: str) -> bool:
    if not body:
        return False
    window = int(getattr(settings, "CHAT_DUPLICATE_WINDOW_SECONDS", 300))
    limit = int(getattr(settings, "CHAT_DUPLICATE_LIMIT", 3))
    since = timezone.now() - timedelta(seconds=window)
    return (
        Message.objects.filter(
            conversation=conversation,
            sender=sender,
            body=body,
            created_at__gte=since,
        ).count()
        >= limit
    )


def _message_content(body: str, image: Image | None, sender, *, allow_empty: bool = False) -> str:
    body = (body or "").strip()
    max_length = int(getattr(settings, "CHAT_MAX_MESSAGE_LENGTH", 2000))
    if len(body) > max_length:
        raise ApiError(
            "That message is too long.",
            code="message_too_long",
            details={"max_length": max_length},
        )
    if not body and image is None and not allow_empty:
        raise ApiError("Write a message or attach a photo.", code="empty_message")
    if image is not None and image.owner_id != sender.pk:
        raise ApiError(
            "That image does not belong to you.", code="image_not_found", status_code=404
        )
    return body


def _create_message_row(
    conversation,
    sender,
    *,
    body: str,
    image: Image | None = None,
    kind: str = MessageKind.TEXT,
    offer: Offer | None = None,
    enforce_first_message: bool = True,
    enforce_duplicate: bool = True,
) -> Message:
    body = _message_content(body, image, sender, allow_empty=offer is not None)
    if enforce_first_message and body and not conversation.messages.exists():
        violations = first_message_violations(body)
        if violations:
            raise ApiError(
                "Phone numbers and links are not allowed in the first message.",
                code="spam_filtered",
                details={"reasons": violations},
            )
    if enforce_duplicate and _duplicate_flood(conversation, sender, body):
        raise ApiError(
            "You are sending the same message repeatedly. Please wait before trying again.",
            code="message_flood",
            status_code=429,
            details={"wait": int(getattr(settings, "CHAT_DUPLICATE_WINDOW_SECONDS", 300))},
        )

    now = timezone.now()
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        kind=kind,
        body=body,
        image=image,
        offer=offer,
        safety_flags=safety_flags(body),
    )
    _last_message_bump(conversation, sender, now)
    transaction.on_commit(lambda: send_new_message_email(message))
    return message


def send_message(conversation, sender, *, body: str = "", image_id: int | None = None) -> Message:
    _assert_can_contact(conversation, sender)
    image = None
    if image_id is not None:
        image = Image.objects.filter(pk=image_id, status=Image.Status.READY).first()
        if image is None:
            raise ApiError(
                "That upload could not be found.", code="image_not_found", status_code=404
            )
    kind = MessageKind.IMAGE if image is not None and not (body or "").strip() else MessageKind.TEXT
    with transaction.atomic():
        return _create_message_row(
            conversation,
            sender,
            body=body,
            image=image,
            kind=kind,
        )


def mark_read(conversation, user, until=None) -> Conversation:
    _assert_can_contact(conversation, user)
    field = "buyer_last_read_at" if user.pk == conversation.buyer_id else "seller_last_read_at"
    Conversation.objects.filter(pk=conversation.pk).update(**{field: until or timezone.now()})
    conversation.refresh_from_db(fields=[field])
    return conversation


def set_archived(conversation, user, archived: bool) -> Conversation:
    if not conversation.is_participant(user):
        raise ApiError(
            "You do not have access to this conversation.",
            code="permission_denied",
            status_code=403,
        )
    field = "buyer_archived" if user.pk == conversation.buyer_id else "seller_archived"
    Conversation.objects.filter(pk=conversation.pk).update(**{field: archived})
    conversation.refresh_from_db(fields=[field])
    return conversation


def create_offer(conversation, creator, amount, note: str = "") -> Offer:
    _assert_can_contact(conversation, creator)
    if conversation.listing.price_mode != PriceMode.NEGOTIABLE:
        raise ApiError(
            "This listing does not accept offers.",
            code="offer_not_allowed",
        )
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if Offer.objects.filter(conversation=locked, status=OfferStatus.PENDING).exists():
            raise ApiError(
                "There is already an open offer in this conversation.",
                code="open_offer_exists",
                status_code=409,
            )
        offer = Offer.objects.create(
            conversation=locked,
            created_by=creator,
            amount=amount,
            currency=locked.listing.currency,
        )
        _create_message_row(
            locked,
            creator,
            body=note,
            kind=MessageKind.OFFER,
            offer=offer,
            enforce_duplicate=False,
        )
    return offer


def _lock_offer(offer_id: int, actor) -> Offer:
    offer = (
        Offer.objects.select_for_update()
        .select_related("conversation", "conversation__seller", "conversation__buyer")
        .filter(pk=offer_id)
        .first()
    )
    if offer is None or not offer.conversation.is_participant(actor):
        raise ApiError("That offer could not be found.", code="not_found", status_code=404)
    _assert_can_contact(offer.conversation, actor)
    if offer.status != OfferStatus.PENDING:
        raise ApiError(
            "This offer is no longer open.",
            code="offer_not_pending",
            status_code=409,
        )
    return offer


def _counter_offer(parent: Offer, actor, amount, note: str = "") -> Offer:
    parent.status = OfferStatus.COUNTERED
    parent.responded_at = timezone.now()
    parent.save(update_fields=["status", "responded_at"])
    offer = Offer.objects.create(
        conversation=parent.conversation,
        created_by=actor,
        amount=amount,
        currency=parent.currency,
        parent=parent,
    )
    _create_message_row(
        parent.conversation,
        actor,
        body=note,
        kind=MessageKind.OFFER,
        offer=offer,
        enforce_duplicate=False,
    )
    return offer


def act_on_offer(offer_id: int, actor, action: str, *, amount=None, note: str = "") -> Offer:
    with transaction.atomic():
        offer = _lock_offer(offer_id, actor)
        is_creator = offer.created_by_id == actor.pk
        if action == "withdraw":
            if not is_creator:
                raise ApiError(
                    "Only the person who made the offer can withdraw it.",
                    code="offer_action_not_allowed",
                    status_code=403,
                )
            offer.status = OfferStatus.WITHDRAWN
            offer.responded_at = timezone.now()
            offer.save(update_fields=["status", "responded_at"])
            return offer
        if is_creator:
            raise ApiError(
                "The other person must respond to this offer.",
                code="offer_action_not_allowed",
                status_code=403,
            )
        if action == "accept":
            offer.status = OfferStatus.ACCEPTED
            offer.responded_at = timezone.now()
            offer.save(update_fields=["status", "responded_at"])
            return offer
        if action == "decline":
            offer.status = OfferStatus.DECLINED
            offer.responded_at = timezone.now()
            offer.save(update_fields=["status", "responded_at"])
            return offer
        if action == "counter":
            if amount is None:
                raise ApiError("Enter a counter-offer amount.", code="bad_request")
            return _counter_offer(offer, actor, amount, note)
        raise ApiError("That offer action is not supported.", code="bad_request")


def reveal_phone(listing, viewer, request) -> str:
    """Return the seller's phone and write the anti-scrape audit row."""
    if listing.seller_id == viewer.pk:
        raise ApiError(
            "You cannot reveal your own phone number.",
            code="cannot_contact_yourself",
        )
    if listing.contact_mode not in (ContactMode.PHONE, ContactMode.WHATSAPP):
        raise ApiError(
            "The seller chose chat only for this listing.",
            code="phone_not_available",
        )
    seller = listing.seller
    if not seller.phone_verified or not seller.phone_number:
        raise ApiError(
            "The seller has not verified a phone number for this listing.",
            code="phone_not_available",
        )
    if users_blocked(seller.pk, viewer.pk):
        raise ApiError(
            "You cannot contact this user because one of you blocked the other.",
            code="user_blocked",
            status_code=403,
        )
    PhoneReveal.objects.create(
        listing=listing,
        viewer=viewer,
        seller=seller,
        phone_number=seller.phone_number,
        ip_address=request.META.get("REMOTE_ADDR") or None,
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
    )
    logger.info(
        "phone revealed listing=%s viewer=%s seller=%s",
        listing.pk,
        viewer.pk,
        seller.pk,
    )
    return seller.phone_number


def block_user(blocker, blocked) -> bool:
    if blocker.pk == blocked.pk:
        raise ApiError("You cannot block yourself.", code="cannot_contact_yourself")
    _, created = UserBlock.objects.get_or_create(blocker=blocker, blocked=blocked)
    if created:
        logger.info("user %s blocked user %s", blocker.pk, blocked.pk)
    return created


def unblock_user(blocker, blocked) -> None:
    UserBlock.objects.filter(blocker=blocker, blocked=blocked).delete()


def create_report(
    reporter,
    *,
    reason: str,
    details: str = "",
    reported_user=None,
    listing=None,
    conversation=None,
    message=None,
) -> Report:
    if message is not None:
        if not message.conversation.is_participant(reporter):
            raise ApiError(
                "That message is not part of your conversation.", code="invalid_report_target"
            )
        conversation = message.conversation
        listing = conversation.listing
        reported_user = conversation.other_user_for(reporter)
    elif conversation is not None:
        if not conversation.is_participant(reporter):
            raise ApiError("That conversation is not yours.", code="invalid_report_target")
        listing = conversation.listing
        reported_user = conversation.other_user_for(reporter)
    elif listing is not None:
        reported_user = listing.seller
    if reported_user is None:
        raise ApiError(
            "Choose the person, listing, or message you want to report.",
            code="report_target_required",
        )
    if reported_user.pk == reporter.pk:
        raise ApiError("You cannot report yourself.", code="cannot_report_yourself")
    return Report.objects.create(
        reporter=reporter,
        reported_user=reported_user,
        listing=listing,
        conversation=conversation,
        message=message,
        reason=reason,
        details=(details or "").strip(),
    )
