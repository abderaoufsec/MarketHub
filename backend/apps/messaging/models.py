"""Contact, chat and offer rows for Phase 16.

The marketplace already had a listing surface (Phase 13) and media (Phase 14).
This app owns the conversation that starts when a buyer contacts a seller:
messages, price offers, blocks, abuse reports, and the audit row written every
time a phone number is revealed.

No websocket server is required for the MVP: the API exposes an ``after``
cursor so the chat page can poll for new messages. The data model is transport
agnostic - Phase 22 can add Channels/push without changing these rows.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConversationQuerySet(models.QuerySet):
    def for_user(self, user):
        """Only conversations where the caller is one of the two people."""
        return self.filter(models.Q(buyer=user) | models.Q(seller=user))


class Conversation(models.Model):
    """One buyer/seller thread about one listing.

    ``(listing, buyer)`` is unique: if the buyer leaves and comes back, the
    same thread (and its history) is reused instead of fragmenting a deal
    across duplicate inbox rows.
    """

    listing = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buyer_conversations",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    #: Denormalized for keyset ordering. Every new message bumps it.
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Read receipts are conversation-level. A user reads the thread up to a
    # point; every message before that point is read for them.
    buyer_last_read_at = models.DateTimeField(null=True, blank=True)
    seller_last_read_at = models.DateTimeField(null=True, blank=True)

    # Archiving is per participant: one side tidying their inbox must not hide
    # the thread from the other side.
    buyer_archived = models.BooleanField(default=False)
    seller_archived = models.BooleanField(default=False)

    objects = ConversationQuerySet.as_manager()

    class Meta:
        db_table = "messaging_conversations"
        ordering = ["-last_message_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "buyer"],
                name="unique_conversation_per_listing_buyer",
            ),
            models.CheckConstraint(
                condition=~models.Q(buyer=models.F("seller")),
                name="conversation_parties_differ",
            ),
        ]
        indexes = [
            models.Index(fields=["buyer", "-last_message_at"], name="conv_buyer_recent"),
            models.Index(fields=["seller", "-last_message_at"], name="conv_seller_recent"),
            models.Index(fields=["-last_message_at"], name="conv_recent"),
        ]

    def __str__(self):
        return f"Conversation {self.pk}: {self.buyer_id} <> {self.seller_id}"

    def participant_ids(self) -> set[int]:
        return {self.buyer_id, self.seller_id}

    def is_participant(self, user) -> bool:
        return bool(
            user and getattr(user, "is_authenticated", False) and user.pk in self.participant_ids()
        )

    def role_for(self, user) -> str | None:
        if not self.is_participant(user):
            return None
        return "buyer" if user.pk == self.buyer_id else "seller"

    def other_user_for(self, user):
        if user.pk == self.buyer_id:
            return self.seller
        if user.pk == self.seller_id:
            return self.buyer
        return None

    def last_read_at_for(self, user):
        return self.buyer_last_read_at if user.pk == self.buyer_id else self.seller_last_read_at

    def other_last_read_at_for(self, user):
        return self.seller_last_read_at if user.pk == self.buyer_id else self.buyer_last_read_at

    def archived_for(self, user) -> bool:
        return self.buyer_archived if user.pk == self.buyer_id else self.seller_archived


class MessageKind(models.TextChoices):
    TEXT = "TEXT", "Text"
    IMAGE = "IMAGE", "Image"
    OFFER = "OFFER", "Offer"
    SYSTEM = "SYSTEM", "System"


class MessageQuerySet(models.QuerySet):
    def visible_to(self, user):
        return self.filter(models.Q(conversation__buyer=user) | models.Q(conversation__seller=user))


class Message(models.Model):
    """A text, photo, or offer message inside a conversation.

    ``safety_flags`` is a denormalized audit trail of the nudges the API
    returned for this body (off-platform payment, suspicious link, phone
    number). Storing it means a report can be reviewed later even if the
    detector changes.
    """

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_chat_messages",
    )
    kind = models.CharField(max_length=16, choices=MessageKind.choices, default=MessageKind.TEXT)
    body = models.TextField(blank=True, default="")
    image = models.ForeignKey(
        "media.Image",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
    )
    # An offer is represented by exactly one message, so the chat sees the
    # negotiation in context instead of in a separate screen.
    offer = models.OneToOneField(
        "Offer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message",
    )
    safety_flags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MessageQuerySet.as_manager()

    class Meta:
        db_table = "messaging_messages"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "id"], name="msg_conversation_id"),
            models.Index(fields=["conversation", "-created_at"], name="msg_conversation_recent"),
            models.Index(fields=["sender", "-created_at"], name="msg_sender_recent"),
        ]

    def __str__(self):
        preview = self.body[:40] if self.body else self.kind
        return f"{self.kind} #{self.pk}: {preview}"


class OfferStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    COUNTERED = "COUNTERED", "Countered"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Offer(models.Model):
    """A price offer; counters form a parent chain.

    Only one offer is PENDING per conversation at a time. That rule lives in
    the service layer (inside a row lock), so accept/counter/decline cannot
    race into two open negotiations.
    """

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_offers",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="DZD")
    status = models.CharField(
        max_length=16,
        choices=OfferStatus.choices,
        default=OfferStatus.PENDING,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "messaging_offers"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["conversation", "status"], name="offer_conversation_status"),
            models.Index(fields=["created_by", "-created_at"], name="offer_creator_recent"),
        ]

    def __str__(self):
        return f"Offer {self.pk} {self.amount} {self.currency} ({self.status})"


class PhoneReveal(models.Model):
    """One row per successful phone reveal (Phase 16 anti-scrape audit).

    The number is snapshotted as well as linked, so changing a verified number
    later does not rewrite history. The row is deliberately immutable through
    the API; only support/admin can inspect it.
    """

    listing = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="phone_reveals",
    )
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="phone_reveals",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_phone_reveals",
    )
    phone_number = models.CharField(max_length=20)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messaging_phone_reveals"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["listing", "-created_at"], name="reveal_listing_recent"),
            models.Index(fields=["viewer", "-created_at"], name="reveal_viewer_recent"),
            models.Index(fields=["seller", "-created_at"], name="reveal_seller_recent"),
        ]

    def __str__(self):
        return f"Reveal {self.listing_id} -> user {self.viewer_id}"


class UserBlock(models.Model):
    """A one-way block. Either direction prevents contact between the pair."""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_made",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messaging_user_blocks"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_user_block",
            ),
            models.CheckConstraint(
                condition=~models.Q(blocker=models.F("blocked")),
                name="user_cannot_block_self",
            ),
        ]
        indexes = [
            models.Index(fields=["blocker", "blocked"], name="block_pair"),
            models.Index(fields=["blocked", "blocker"], name="block_reverse"),
        ]

    def __str__(self):
        return f"{self.blocker_id} blocked {self.blocked_id}"


class ReportReason(models.TextChoices):
    SPAM = "SPAM", "Spam"
    SCAM = "SCAM", "Scam or fraud"
    HARASSMENT = "HARASSMENT", "Harassment"
    PROHIBITED_ITEM = "PROHIBITED_ITEM", "Prohibited item"
    OTHER = "OTHER", "Other"


class ReportStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    REVIEWED = "REVIEWED", "Reviewed"
    DISMISSED = "DISMISSED", "Dismissed"


class Report(models.Model):
    """An abuse report from a conversation, message, listing, or profile."""

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )
    listing = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    reason = models.CharField(max_length=24, choices=ReportReason.choices)
    details = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=ReportStatus.choices,
        default=ReportStatus.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "messaging_reports"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reporter=models.F("reported_user")),
                name="report_parties_differ",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="report_status_recent"),
            models.Index(fields=["reported_user", "-created_at"], name="report_user_recent"),
        ]

    def __str__(self):
        return f"Report {self.pk}: {self.reason} on user {self.reported_user_id}"
