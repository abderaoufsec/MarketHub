"""Trust & safety API (Phase 17)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.models import Report, ReportStatus
from apps.products.models import Product
from core.exceptions import ApiError

from .blocklists import add_entry, expire_due_entries, matching_entries
from .models import (
    Appeal,
    AppealStatus,
    BlocklistEntry,
    BlocklistKind,
    ModerationAuditLog,
    SellerVerification,
    VerificationStatus,
)
from .reputation import compute_reputation
from .safety import safety_center_payload
from .serializers import (
    AppealActionSerializer,
    AppealCreateSerializer,
    AppealSerializer,
    BlocklistEntrySerializer,
    MassActionSerializer,
    ReportActionSerializer,
    ReportAdminSerializer,
    ReputationSerializer,
    StoreVerificationCreateSerializer,
    VerificationActionSerializer,
    VerificationCreateSerializer,
    VerificationSerializer,
)
from .services import (
    create_appeal,
    detect_ban_evasion,
    mass_action,
    review_appeal,
    review_report,
    review_verification,
    submit_identity_verification,
    submit_store_verification,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Public / seller-facing
# ---------------------------------------------------------------------------
class SafetyCenterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(safety_center_payload())


class SellerReputationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: ReputationSerializer})
    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id, is_active=True)
        return Response(compute_reputation(user))


class MyVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: VerificationSerializer(many=True)})
    def get(self, request):
        rows = SellerVerification.objects.filter(user=request.user).select_related(
            "document_image", "selfie_image", "store"
        )
        return Response(VerificationSerializer(rows, many=True, context={"request": request}).data)

    @extend_schema(
        request=VerificationCreateSerializer,
        responses={201: VerificationSerializer},
    )
    def post(self, request):
        payload = VerificationCreateSerializer(data=request.data, context={"request": request})
        payload.is_valid(raise_exception=True)
        verification = submit_identity_verification(request.user, payload.validated_data)
        return Response(
            VerificationSerializer(verification, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MyStoreVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=StoreVerificationCreateSerializer,
        responses={201: VerificationSerializer},
    )
    def post(self, request):
        payload = StoreVerificationCreateSerializer(data=request.data, context={"request": request})
        payload.is_valid(raise_exception=True)
        verification = submit_store_verification(request.user, payload.validated_data)
        return Response(
            VerificationSerializer(verification, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AppealListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AppealSerializer(many=True)})
    def get(self, request):
        rows = Appeal.objects.filter(user=request.user).select_related("listing", "review")
        return Response(AppealSerializer(rows, many=True).data)

    @extend_schema(request=AppealCreateSerializer, responses={201: AppealSerializer})
    def post(self, request):
        payload = AppealCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        appeal = create_appeal(
            request.user,
            kind=data["kind"],
            message=data["message"],
            listing=data.get("listing"),
            review=data.get("review"),
        )
        return Response(AppealSerializer(appeal).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Staff moderation API
# ---------------------------------------------------------------------------
class AdminOverviewView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        expire_due_entries()
        now = timezone.now()
        return Response(
            {
                "open_reports": Report.objects.filter(status=ReportStatus.OPEN).count(),
                "overdue_reports": Report.objects.filter(
                    status=ReportStatus.OPEN, sla_due_at__lte=now
                ).count(),
                "pending_verifications": SellerVerification.objects.filter(
                    status=VerificationStatus.PENDING
                ).count(),
                "open_appeals": Appeal.objects.filter(status=AppealStatus.OPEN).count(),
                "active_blocklist": BlocklistEntry.objects.active().count(),
                "listings_flagged": Product.objects.exclude(moderation_flags=[]).count(),
            }
        )


class AdminVerificationListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: VerificationSerializer(many=True)})
    def get(self, request):
        status_filter = request.query_params.get("status") or VerificationStatus.PENDING
        if status_filter not in VerificationStatus.values:
            raise ApiError("Unknown verification status.", code="validation_error")
        rows = (
            SellerVerification.objects.filter(status=status_filter)
            .select_related("user", "document_image", "selfie_image", "store")
            .order_by("submitted_at")[:200]
        )
        return Response(VerificationSerializer(rows, many=True, context={"request": request}).data)


class AdminVerificationActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(request=VerificationActionSerializer, responses={200: VerificationSerializer})
    def post(self, request, pk):
        payload = VerificationActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        verification = get_object_or_404(SellerVerification, pk=pk)
        verification = review_verification(
            verification,
            actor=request.user,
            approve=payload.validated_data["action"] == "approve",
            reason=payload.validated_data.get("reason", ""),
        )
        return Response(VerificationSerializer(verification, context={"request": request}).data)


class AdminReportListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: ReportAdminSerializer(many=True)})
    def get(self, request):
        queryset = Report.objects.select_related("reporter", "reported_user", "listing").order_by(
            "sla_due_at", "-created_at"
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in ReportStatus.values:
                raise ApiError("Unknown report status.", code="validation_error")
            queryset = queryset.filter(status=status_filter)
        if request.query_params.get("overdue") in ("1", "true", "True"):
            queryset = queryset.filter(status=ReportStatus.OPEN, sla_due_at__lte=timezone.now())
        target = request.query_params.get("target_type")
        if target == "listing":
            queryset = queryset.filter(listing__isnull=False)
        elif target == "user":
            queryset = queryset.filter(listing__isnull=True, message__isnull=True)
        return Response(
            ReportAdminSerializer(queryset[:200], many=True, context={"request": request}).data
        )


class AdminReportActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(request=ReportActionSerializer, responses={200: ReportAdminSerializer})
    def post(self, request, pk):
        payload = ReportActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        report = get_object_or_404(
            Report.objects.select_related("reporter", "reported_user", "listing"),
            pk=pk,
        )
        report = review_report(
            report,
            actor=request.user,
            action=payload.validated_data["action"],
            resolution=payload.validated_data.get("resolution", ""),
            action_taken=payload.validated_data.get("action_taken", ""),
        )
        return Response(ReportAdminSerializer(report, context={"request": request}).data)


class AdminAppealListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: AppealSerializer(many=True)})
    def get(self, request):
        rows = Appeal.objects.select_related("user", "listing", "review").order_by("created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in AppealStatus.values:
                raise ApiError("Unknown appeal status.", code="validation_error")
            rows = rows.filter(status=status_filter)
        return Response(AppealSerializer(rows[:200], many=True).data)


class AdminAppealActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(request=AppealActionSerializer, responses={200: AppealSerializer})
    def post(self, request, pk):
        payload = AppealActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        appeal = get_object_or_404(Appeal, pk=pk)
        appeal = review_appeal(
            appeal,
            actor=request.user,
            approve=payload.validated_data["action"] == "approve",
            resolution=payload.validated_data.get("resolution", ""),
        )
        return Response(AppealSerializer(appeal).data)


class AdminBlocklistView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: BlocklistEntrySerializer(many=True)})
    def get(self, request):
        expire_due_entries()
        rows = BlocklistEntry.objects.select_related("created_by").order_by("-created_at")
        kind = request.query_params.get("kind")
        if kind:
            if kind not in BlocklistKind.values:
                raise ApiError("Unknown blocklist kind.", code="validation_error")
            rows = rows.filter(kind=kind)
        if request.query_params.get("active") in ("1", "true", "True"):
            rows = rows.active()
        return Response(BlocklistEntrySerializer(rows[:200], many=True).data)

    @extend_schema(request=BlocklistEntrySerializer, responses={201: BlocklistEntrySerializer})
    def post(self, request):
        payload = BlocklistEntrySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        entry = add_entry(
            kind=payload.validated_data["kind"],
            value=payload.validated_data["value"],
            reason=payload.validated_data.get("reason", ""),
            created_by=request.user,
            expires_at=payload.validated_data.get("expires_at"),
            metadata=payload.validated_data.get("metadata", {}),
        )
        return Response(BlocklistEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class AdminBlocklistDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=BlocklistEntrySerializer,
        responses={200: BlocklistEntrySerializer},
    )
    def patch(self, request, pk):
        entry = get_object_or_404(BlocklistEntry, pk=pk)
        payload = BlocklistEntrySerializer(entry, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        payload.save()
        return Response(payload.data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        entry = get_object_or_404(BlocklistEntry, pk=pk)
        entry.is_active = False
        entry.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMassActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(request=MassActionSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        payload = MassActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = mass_action(
            payload.validated_data["identifier"],
            action=payload.validated_data["action"],
            actor=request.user,
            reason=payload.validated_data.get("reason", ""),
        )
        return Response(result)


class AdminAuditLogView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        rows = ModerationAuditLog.objects.select_related("actor").order_by("-created_at")[:200]
        return Response(
            [
                {
                    "id": row.pk,
                    "actor": row.actor_id,
                    "actor_email": row.actor.email if row.actor else None,
                    "action": row.action,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "reason": row.reason,
                    "metadata": row.metadata,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        )


class AdminBanEvasionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        user_id = request.query_params.get("user_id")
        phone = request.query_params.get("phone")
        if user_id:
            user = get_object_or_404(User, pk=user_id)
            payload = detect_ban_evasion(user, request)
        elif phone:
            payload = {
                "phone": phone,
                "matches": (
                    BlocklistEntrySerializer(
                        matching_entries(BlocklistKind.PHONE, phone), many=True
                    ).data
                ),
                "accounts": list(
                    User.objects.filter(Q(phone_number=phone) | Q(username=phone)).values(
                        "id", "email", "phone_number", "is_active"
                    )[:20]
                ),
            }
        else:
            raise ApiError("Pass a user_id or a phone.", code="validation_error")
        return Response(payload)
