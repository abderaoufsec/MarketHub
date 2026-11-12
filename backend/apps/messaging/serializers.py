"""Chat API serializers (Phase 16)."""

from __future__ import annotations

from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.media.serializers import ImageSerializer

from .models import (
    Conversation,
    Message,
    Offer,
    Report,
    ReportReason,
)


class ChatUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        if obj.email:
            return obj.email.split("@")[0]
        return obj.username


class ListingPreviewSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
    price_mode = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    canonical_path = serializers.CharField(read_only=True)
    primary_image = serializers.SerializerMethodField()

    def get_primary_image(self, obj) -> str | None:
        images = list(obj.images.all())  # prefetched by the view
        if not images:
            return None
        primary = next((image for image in images if image.is_primary), images[0])
        return primary.url_for("card", request=self.context.get("request"))


class OfferSerializer(serializers.ModelSerializer):
    created_by = serializers.IntegerField(source="created_by_id", read_only=True)
    parent = serializers.IntegerField(source="parent_id", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "amount",
            "currency",
            "status",
            "created_by",
            "parent",
            "created_at",
            "responded_at",
        ]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    sender = ChatUserSerializer(read_only=True)
    image = ImageSerializer(read_only=True)
    offer = OfferSerializer(read_only=True)
    is_read = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation",
            "sender",
            "kind",
            "body",
            "image",
            "offer",
            "safety_flags",
            "created_at",
            "is_read",
            "read_at",
        ]
        read_only_fields = fields

    def _is_for_viewer(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.pk == obj.sender_id)

    def get_is_read(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if self._is_for_viewer(obj):
            read_at = obj.conversation.other_last_read_at_for(request.user)
        else:
            read_at = obj.conversation.last_read_at_for(request.user)
        return bool(read_at and read_at >= obj.created_at)

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_read_at(self, obj) -> str | None:
        request = self.context.get("request")
        if not request or request.user.pk != obj.sender_id:
            return None
        read_at = obj.conversation.other_last_read_at_for(request.user)
        return read_at if read_at and read_at >= obj.created_at else None


class ConversationSerializer(serializers.ModelSerializer):
    listing = ListingPreviewSerializer(read_only=True)
    buyer = ChatUserSerializer(read_only=True)
    seller = ChatUserSerializer(read_only=True)
    other_user = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True)
    is_archived = serializers.SerializerMethodField()
    is_blocked = serializers.BooleanField(read_only=True)
    can_send = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "listing",
            "buyer",
            "seller",
            "other_user",
            "role",
            "last_message",
            "last_message_at",
            "unread_count",
            "is_archived",
            "is_blocked",
            "can_send",
            "buyer_last_read_at",
            "seller_last_read_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _user(self):
        request = self.context.get("request")
        return request.user if request else None

    @extend_schema_field(ChatUserSerializer)
    def get_other_user(self, obj):
        user = self._user()
        return ChatUserSerializer(obj.other_user_for(user)).data if user else None

    def get_role(self, obj) -> str | None:
        user = self._user()
        return obj.role_for(user) if user else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_last_message(self, obj):
        message_id = getattr(obj, "last_message_id", None)
        if message_id is None:
            return None
        return {
            "id": message_id,
            "body": getattr(obj, "last_message_body", "") or "",
            "kind": getattr(obj, "last_message_kind", "TEXT"),
            "sender_id": getattr(obj, "last_message_sender_id", None),
            "offer_amount": getattr(obj, "last_message_offer_amount", None),
            "created_at": getattr(obj, "last_message_created_at", None),
        }

    def get_is_archived(self, obj) -> bool:
        user = self._user()
        return obj.archived_for(user) if user else False

    def get_can_send(self, obj) -> bool:
        return not bool(getattr(obj, "is_blocked", False))


class ConversationCreateSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(min_value=1)


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="")
    image_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs):
        if not (attrs.get("body") or "").strip() and not attrs.get("image_id"):
            raise serializers.ValidationError({"body": "Write a message or attach a photo."})
        return attrs


class OfferCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
    )
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class OfferActionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("1.00"),
        required=False,
    )
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)

    def validate(self, attrs):
        if self.context.get("action") == "counter" and attrs.get("amount") is None:
            raise serializers.ValidationError({"amount": "Enter a counter-offer amount."})
        return attrs


class ConversationArchiveSerializer(serializers.Serializer):
    is_archived = serializers.BooleanField()


class ReportCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReportReason.choices)
    details = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    reported_user_id = serializers.IntegerField(required=False, min_value=1)
    listing_id = serializers.IntegerField(required=False, min_value=1)
    conversation_id = serializers.IntegerField(required=False, min_value=1)
    message_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if not any(
            attrs.get(field)
            for field in ("reported_user_id", "listing_id", "conversation_id", "message_id")
        ):
            raise serializers.ValidationError(
                {"reported_user_id": "Choose the person or content you want to report."}
            )
        return attrs


class OfferResponseSerializer(serializers.Serializer):
    """OpenAPI-only shape for actions that return a refreshed offer."""

    offer = OfferSerializer(read_only=True)
    message = MessageSerializer(read_only=True)
    status = serializers.CharField(read_only=True)


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reported_user",
            "listing",
            "conversation",
            "message",
            "reason",
            "details",
            "status",
            "created_at",
        ]
        read_only_fields = fields
