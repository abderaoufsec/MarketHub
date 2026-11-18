"""API shapes for trust & safety (Phase 17)."""

from __future__ import annotations

from rest_framework import serializers

from apps.media.models import Image
from apps.media.serializers import ImageSerializer
from apps.messaging.models import Report
from apps.products.models import Product, ProductReview
from core.i18n import choice_label

from .models import (
    Appeal,
    AppealKind,
    BlocklistEntry,
    BlocklistKind,
    SanctionKind,
    SellerVerification,
    VerificationStatus,
)


class VerificationCreateSerializer(serializers.Serializer):
    document_image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source="document_image",
        required=False,
        allow_null=True,
    )
    selfie_image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source="selfie_image",
        required=False,
        allow_null=True,
    )
    document_type = serializers.CharField(max_length=32, required=False, default="ID_CARD")
    document_number = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        request = self.context.get("request")
        for field in ("document_image", "selfie_image"):
            image = attrs.get(field)
            if image is not None and request is not None and image.owner_id != request.user.pk:
                raise serializers.ValidationError(
                    {field.replace("_image", "_image_id"): "That image does not belong to you."}
                )
        if attrs.get("document_image") is None:
            raise serializers.ValidationError(
                {"document_image_id": "Upload a photo of your ID or passport."}
            )
        return attrs


class StoreVerificationCreateSerializer(serializers.Serializer):
    document_image_id = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.all(),
        source="document_image",
        required=False,
        allow_null=True,
    )
    document_type = serializers.CharField(
        max_length=32, required=False, default="COMMERCIAL_REGISTER"
    )
    commercial_register_number = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    nif_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        request = self.context.get("request")
        image = attrs.get("document_image")
        if image is not None and request is not None and image.owner_id != request.user.pk:
            raise serializers.ValidationError(
                {"document_image_id": "That image does not belong to you."}
            )
        if not (
            (attrs.get("commercial_register_number") or "").strip()
            or (attrs.get("nif_number") or "").strip()
        ):
            raise serializers.ValidationError(
                {"commercial_register_number": "Provide a commercial register number or a NIF."}
            )
        return attrs


class VerificationSerializer(serializers.ModelSerializer):
    status_label = serializers.SerializerMethodField()
    kind_label = serializers.SerializerMethodField()
    document_image = ImageSerializer(read_only=True)
    selfie_image = ImageSerializer(read_only=True)
    store_name = serializers.CharField(source="store.store_name", read_only=True, allow_null=True)

    class Meta:
        model = SellerVerification
        fields = [
            "id",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "document_type",
            "document_number",
            "commercial_register_number",
            "nif_number",
            "document_image",
            "selfie_image",
            "store",
            "store_name",
            "submitted_at",
            "updated_at",
            "reviewed_at",
            "rejection_reason",
        ]
        read_only_fields = fields

    def get_status_label(self, obj) -> str:
        return choice_label(VerificationStatus.choices, obj.status)

    def get_kind_label(self, obj) -> str:
        from .models import VerificationKind

        return choice_label(VerificationKind.choices, obj.kind)


class VerificationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class BlocklistEntrySerializer(serializers.ModelSerializer):
    kind_label = serializers.SerializerMethodField()
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, allow_null=True
    )

    class Meta:
        model = BlocklistEntry
        fields = [
            "id",
            "kind",
            "kind_label",
            "value",
            "reason",
            "is_active",
            "expires_at",
            "metadata",
            "created_by",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = ["id", "is_active", "created_by", "created_at"]

    def get_kind_label(self, obj) -> str:
        return choice_label(BlocklistKind.choices, obj.kind)

    def validate_kind(self, value):
        if value not in BlocklistKind.values:
            raise serializers.ValidationError("Unknown blocklist kind.")
        return value


class ReportAdminSerializer(serializers.ModelSerializer):
    reporter_email = serializers.CharField(source="reporter.email", read_only=True)
    reported_user_email = serializers.CharField(source="reported_user.email", read_only=True)
    listing_name = serializers.CharField(source="listing.name", read_only=True, allow_null=True)
    target_type = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    reason_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reporter_email",
            "reported_user",
            "reported_user_email",
            "listing",
            "listing_name",
            "conversation",
            "message",
            "target_type",
            "reason",
            "reason_label",
            "details",
            "status",
            "status_label",
            "sla_due_at",
            "is_overdue",
            "created_at",
            "reviewed_at",
            "resolution",
            "action_taken",
        ]
        read_only_fields = fields

    def get_reason_label(self, obj) -> str:
        from apps.messaging.models import ReportReason

        return choice_label(ReportReason.choices, obj.reason)

    def get_status_label(self, obj) -> str:
        from apps.messaging.models import ReportStatus

        return choice_label(ReportStatus.choices, obj.status)


class ReportActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["review", "dismiss", "action"])
    action_taken = serializers.ChoiceField(
        choices=["", "listing_removed", "user_banned", "user_suspended"],
        required=False,
        allow_blank=True,
        default="",
    )
    resolution = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=4000
    )


class AppealCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=AppealKind.choices)
    listing_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="listing",
        required=False,
        allow_null=True,
    )
    review_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductReview.objects.all(),
        source="review",
        required=False,
        allow_null=True,
    )
    message = serializers.CharField(max_length=4000)

    def validate(self, attrs):
        if attrs["kind"] == AppealKind.LISTING and attrs.get("listing") is None:
            raise serializers.ValidationError({"listing_id": "Choose the listing to appeal."})
        if attrs["kind"] == AppealKind.REVIEW and attrs.get("review") is None:
            raise serializers.ValidationError({"review_id": "Choose the review to appeal."})
        return attrs


class AppealSerializer(serializers.ModelSerializer):
    status_label = serializers.SerializerMethodField()
    kind_label = serializers.SerializerMethodField()
    listing_name = serializers.CharField(source="listing.name", read_only=True, allow_null=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Appeal
        fields = [
            "id",
            "user",
            "user_email",
            "kind",
            "kind_label",
            "listing",
            "listing_name",
            "review",
            "message",
            "status",
            "status_label",
            "resolution",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_status_label(self, obj) -> str:
        from .models import AppealStatus

        return choice_label(AppealStatus.choices, obj.status)

    def get_kind_label(self, obj) -> str:
        return choice_label(AppealKind.choices, obj.kind)


class AppealActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    resolution = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=4000
    )


class MassActionSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        max_length=64,
        help_text="A user id or a phone number shared by several accounts.",
    )
    action = serializers.ChoiceField(choices=["ban", "suspend", "warn", "reinstate"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class SanctionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=SanctionKind.choices)
    reason = serializers.CharField()
    is_active = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class ReputationSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    tier = serializers.CharField()
    tier_label = serializers.CharField()
    badges = serializers.ListField(child=serializers.DictField())
    completed_orders = serializers.IntegerField()
    response_rate = serializers.FloatField()
    response_samples = serializers.IntegerField()
    reports_received = serializers.IntegerField()
    account_age_days = serializers.IntegerField()
    breakdown = serializers.DictField()
