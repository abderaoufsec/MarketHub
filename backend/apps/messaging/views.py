"""Chat, offer and moderation API (Phase 16).

All endpoints are authenticated except none: even reading a thread exposes two
people's messages. A conversation is scoped to its participants in the queryset,
so a stranger receives 404 rather than a probe-able 403.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    When,
)
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import Product
from core.exceptions import ApiError

from .models import Conversation, Message, UserBlock
from .serializers import (
    ConversationArchiveSerializer,
    ConversationCreateSerializer,
    ConversationSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    OfferActionSerializer,
    OfferCreateSerializer,
    OfferSerializer,
    ReportCreateSerializer,
    ReportSerializer,
)
from .services import (
    act_on_offer,
    block_user,
    create_offer,
    create_report,
    get_or_create_conversation,
    mark_read,
    send_message,
    set_archived,
    unblock_user,
)
from .throttles import (
    ConversationCreateRateThrottle,
    MessageRateThrottle,
    OfferRateThrottle,
    ReportRateThrottle,
)

User = get_user_model()

CONVERSATION_NOT_FOUND = "That conversation could not be found."


def _annotate_conversations(queryset, user):
    """Add the inbox fields (last message, unread count, block state) in SQL.

    A page of conversations must not run four queries per row. The Subqueries
    read the newest message off the ``(conversation, -id)`` index; the Count
    joins messages once and is filtered by the viewer's read cursor.
    """
    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-id")
    user_block = UserBlock.objects.filter(
        Q(blocker=user) & (Q(blocked=OuterRef("buyer")) | Q(blocked=OuterRef("seller")))
        | Q(blocked=user) & (Q(blocker=OuterRef("buyer")) | Q(blocker=OuterRef("seller")))
    )
    unread_buyer = ~Q(messages__sender_id=user.pk) & (
        Q(buyer_last_read_at__isnull=True) | Q(messages__created_at__gt=F("buyer_last_read_at"))
    )
    unread_seller = ~Q(messages__sender_id=user.pk) & (
        Q(seller_last_read_at__isnull=True) | Q(messages__created_at__gt=F("seller_last_read_at"))
    )
    return queryset.annotate(
        last_message_id=Subquery(last.values("id")[:1]),
        last_message_body=Subquery(last.values("body")[:1]),
        last_message_kind=Subquery(last.values("kind")[:1]),
        last_message_sender_id=Subquery(last.values("sender_id")[:1]),
        last_message_offer_amount=Subquery(last.values("offer__amount")[:1]),
        last_message_created_at=Subquery(last.values("created_at")[:1]),
        unread_buyer=Count("messages", filter=unread_buyer, distinct=True),
        unread_seller=Count("messages", filter=unread_seller, distinct=True),
        is_blocked=Exists(user_block),
    ).annotate(
        unread_count=Case(
            When(buyer_id=user.pk, then=F("unread_buyer")),
            default=F("unread_seller"),
            output_field=IntegerField(),
        )
    )


def _conversations_for(user):
    return (
        Conversation.objects.for_user(user)
        .select_related("listing", "buyer", "seller")
        .prefetch_related(
            "listing__images",
            "listing__images__upload",
        )
    )


def _conversation_for(user, pk):
    queryset = _annotate_conversations(_conversations_for(user), user)
    return get_object_or_404(queryset, pk=pk)


def _serialize_conversation(conversation, request):
    return ConversationSerializer(conversation, context={"request": request})


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == "POST":
            return [ConversationCreateRateThrottle()]
        return []

    @extend_schema(responses={200: ConversationSerializer(many=True)})
    def get(self, request):
        role = request.query_params.get("role")
        archived = request.query_params.get("archived") in ("1", "true", "True")
        queryset = _conversations_for(request.user)
        if role == "buyer":
            queryset = queryset.filter(buyer=request.user)
        elif role == "seller":
            queryset = queryset.filter(seller=request.user)
        queryset = queryset.filter(
            Q(buyer=request.user, buyer_archived=archived)
            | Q(seller=request.user, seller_archived=archived)
        )
        queryset = _annotate_conversations(queryset, request.user).order_by(
            "-last_message_at", "-id"
        )[:100]
        return Response(
            ConversationSerializer(queryset, many=True, context={"request": request}).data
        )

    @extend_schema(
        request=ConversationCreateSerializer,
        responses={200: ConversationSerializer, 201: ConversationSerializer},
    )
    def post(self, request):
        payload = ConversationCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        conversation, created = get_or_create_conversation(
            payload.validated_data["listing_id"], request.user
        )
        conversation = _conversation_for(request.user, conversation.pk)
        return Response(
            _serialize_conversation(conversation, request).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ConversationSerializer})
    def get(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        return Response(_serialize_conversation(conversation, request).data)

    @extend_schema(
        request=ConversationArchiveSerializer,
        responses={200: ConversationSerializer},
    )
    def patch(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        payload = ConversationArchiveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        set_archived(conversation, request.user, payload.validated_data["is_archived"])
        conversation = _conversation_for(request.user, pk)
        return Response(_serialize_conversation(conversation, request).data)


class ConversationMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == "POST":
            return [MessageRateThrottle()]
        return []

    @staticmethod
    def _cursor(value, name):
        """Turn a query cursor into an int, or refuse it as bad input."""
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ApiError(f"Invalid {name} cursor.", code="validation_error") from None

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        queryset = conversation.messages.select_related("sender", "image", "offer").order_by("id")
        try:
            limit = int(request.query_params.get("limit", 50) or 50)
        except ValueError:
            limit = 50
        limit = min(max(limit, 1), 100)
        after = self._cursor(request.query_params.get("after"), "after")
        before = self._cursor(request.query_params.get("before"), "before")

        if after:
            rows = list(queryset.filter(id__gt=after)[: limit + 1])
            has_more = len(rows) > limit
            rows = rows[:limit]
        else:
            if before:
                queryset = queryset.filter(id__lt=before)
            rows = list(queryset.order_by("-id")[: limit + 1])
            has_more = len(rows) > limit
            rows = list(reversed(rows[:limit]))

        payload = MessageSerializer(rows, many=True, context={"request": request}).data
        return Response(
            {
                "results": payload,
                "next_after": rows[-1].id if rows else None,
                "has_more": has_more,
            }
        )

    @extend_schema(request=MessageCreateSerializer, responses={201: MessageSerializer})
    def post(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        payload = MessageCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message = send_message(
            conversation,
            request.user,
            body=payload.validated_data.get("body", ""),
            image_id=payload.validated_data.get("image_id"),
        )
        message = Message.objects.select_related("sender", "image", "offer", "conversation").get(
            pk=message.pk
        )
        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: ConversationSerializer})
    def post(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        mark_read(conversation, request.user)
        conversation = _conversation_for(request.user, pk)
        return Response(_serialize_conversation(conversation, request).data)


class ConversationOffersView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [OfferRateThrottle]

    @extend_schema(request=OfferCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        conversation = _conversation_for(request.user, pk)
        payload = OfferCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        offer = create_offer(
            conversation,
            request.user,
            payload.validated_data["amount"],
            payload.validated_data.get("note", ""),
        )
        message = Message.objects.select_related("sender", "image", "offer").get(offer=offer)
        return Response(
            {
                "offer": OfferSerializer(offer).data,
                "message": MessageSerializer(message, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class OfferActionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [OfferRateThrottle]

    @extend_schema(request=OfferActionSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk, action):
        if action not in {"accept", "decline", "counter", "withdraw"}:
            raise ApiError("That offer action is not supported.", code="bad_request")
        payload = OfferActionSerializer(
            data=request.data,
            context={"action": action},
        )
        payload.is_valid(raise_exception=True)
        offer = act_on_offer(
            pk,
            request.user,
            action,
            amount=payload.validated_data.get("amount"),
            note=payload.validated_data.get("note", ""),
        )
        message = (
            Message.objects.select_related("sender", "image", "offer").filter(offer=offer).first()
        )
        return Response(
            {
                "offer": OfferSerializer(offer).data,
                "message": (
                    MessageSerializer(message, context={"request": request}).data
                    if message
                    else None
                ),
            }
        )


class BlockUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, pk):
        blocked = get_object_or_404(User, pk=pk, is_active=True)
        created = block_user(request.user, blocked)
        return Response({"blocked": True, "user_id": blocked.pk, "created": created})

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def delete(self, request, pk):
        blocked = get_object_or_404(User, pk=pk)
        unblock_user(request.user, blocked)
        return Response({"blocked": False, "user_id": blocked.pk})


class BlockListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        rows = UserBlock.objects.filter(blocker=request.user).select_related("blocked")
        return Response(
            [
                {
                    "user_id": row.blocked_id,
                    "name": row.blocked.get_full_name() or row.blocked.username,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        )


class ReportCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ReportRateThrottle]

    @extend_schema(request=ReportCreateSerializer, responses={201: ReportSerializer})
    def post(self, request):
        payload = ReportCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        reported_user = None
        if data.get("reported_user_id"):
            reported_user = User.objects.filter(pk=data["reported_user_id"]).first()
            if reported_user is None:
                raise ApiError("That user could not be found.", code="invalid_report_target")
        listing = None
        if data.get("listing_id"):
            listing = Product.objects.filter(pk=data["listing_id"]).select_related("seller").first()
            if listing is None:
                raise ApiError("That listing could not be found.", code="invalid_report_target")
        conversation = None
        if data.get("conversation_id"):
            conversation = _conversation_for(request.user, data["conversation_id"])
        message = None
        if data.get("message_id"):
            message = (
                Message.objects.visible_to(request.user)
                .select_related("conversation")
                .filter(pk=data["message_id"])
                .first()
            )
            if message is None:
                raise ApiError("That message could not be found.", code="invalid_report_target")

        report = create_report(
            request.user,
            reason=data["reason"],
            details=data.get("details", ""),
            reported_user=reported_user,
            listing=listing,
            conversation=conversation,
            message=message,
        )
        return Response(
            ReportSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        buyer_unread = (
            Message.objects.filter(
                conversation__buyer=request.user,
            )
            .exclude(sender=request.user)
            .filter(
                Q(conversation__buyer_last_read_at__isnull=True)
                | Q(created_at__gt=F("conversation__buyer_last_read_at"))
            )
        )
        seller_unread = (
            Message.objects.filter(
                conversation__seller=request.user,
            )
            .exclude(sender=request.user)
            .filter(
                Q(conversation__seller_last_read_at__isnull=True)
                | Q(created_at__gt=F("conversation__seller_last_read_at"))
            )
        )
        buyer_count = buyer_unread.count()
        seller_count = seller_unread.count()
        return Response(
            {
                "unread_count": buyer_count + seller_count,
                "buyer_unread": buyer_count,
                "seller_unread": seller_count,
            }
        )
