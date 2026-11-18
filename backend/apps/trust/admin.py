"""Django admin for trust & safety (Phase 17)."""

from django.contrib import admin

from .models import (
    AccountSanction,
    Appeal,
    BlocklistEntry,
    ModerationAuditLog,
    SellerVerification,
)
from .services import review_appeal, review_verification


@admin.register(SellerVerification)
class SellerVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "kind",
        "status",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
    )
    list_filter = ("kind", "status", "submitted_at")
    search_fields = ("user__email", "user__phone_number", "document_number", "nif_number")
    raw_id_fields = ("user", "document_image", "selfie_image", "store", "reviewed_by")
    readonly_fields = ("submitted_at", "updated_at", "reviewed_at")
    actions = ["approve_verifications", "reject_verifications"]

    def approve_verifications(self, request, queryset):
        handled = 0
        for row in queryset.filter(status="PENDING"):
            review_verification(row, actor=request.user, approve=True)
            handled += 1
        self.message_user(request, f"{handled} verification(s) approved.")

    approve_verifications.short_description = "Approve selected verifications"

    def reject_verifications(self, request, queryset):
        handled = 0
        for row in queryset.filter(status="PENDING"):
            review_verification(
                row,
                actor=request.user,
                approve=False,
                reason="Rejected from the Django admin.",
            )
            handled += 1
        self.message_user(request, f"{handled} verification(s) rejected.")

    reject_verifications.short_description = "Reject selected verifications"


@admin.register(BlocklistEntry)
class BlocklistEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "value", "reason", "is_active", "expires_at", "created_at")
    list_filter = ("kind", "is_active")
    search_fields = ("value", "reason")
    raw_id_fields = ("created_by",)
    readonly_fields = ("created_at",)


@admin.register(AccountSanction)
class AccountSanctionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "is_active", "expires_at", "created_at", "created_by")
    list_filter = ("kind", "is_active")
    search_fields = ("user__email", "user__phone_number", "reason")
    raw_id_fields = ("user", "created_by")
    readonly_fields = ("created_at", "lifted_at")


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "status", "created_at", "reviewed_at")
    list_filter = ("kind", "status")
    search_fields = ("user__email", "message", "resolution")
    raw_id_fields = ("user", "listing", "review", "reviewed_by")
    readonly_fields = ("created_at", "reviewed_at")
    actions = ["approve_appeals", "reject_appeals"]

    def approve_appeals(self, request, queryset):
        handled = 0
        for appeal in queryset.filter(status="OPEN"):
            review_appeal(appeal, actor=request.user, approve=True, resolution="Approved in admin.")
            handled += 1
        self.message_user(request, f"{handled} appeal(s) approved.")

    approve_appeals.short_description = "Approve selected appeals"

    def reject_appeals(self, request, queryset):
        handled = 0
        for appeal in queryset.filter(status="OPEN"):
            review_appeal(
                appeal, actor=request.user, approve=False, resolution="Rejected in admin."
            )
            handled += 1
        self.message_user(request, f"{handled} appeal(s) rejected.")

    reject_appeals.short_description = "Reject selected appeals"


@admin.register(ModerationAuditLog)
class ModerationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "actor", "target_type", "target_id", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("actor__email", "reason", "target_type")
    raw_id_fields = ("actor",)
    readonly_fields = (
        "actor",
        "action",
        "target_type",
        "target_id",
        "reason",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
