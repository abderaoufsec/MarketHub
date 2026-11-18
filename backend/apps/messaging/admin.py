from django.contrib import admin

from .models import Conversation, Message, Offer, PhoneReveal, Report, UserBlock


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "buyer", "seller", "last_message_at")
    search_fields = ("listing__name", "buyer__email", "seller__email")
    raw_id_fields = ("listing", "buyer", "seller")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "kind", "created_at")
    list_filter = ("kind",)
    search_fields = ("body", "sender__email")
    raw_id_fields = ("conversation", "sender", "image", "offer")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "created_by", "amount", "currency", "status")
    list_filter = ("status", "currency")
    raw_id_fields = ("conversation", "created_by", "parent")


@admin.register(PhoneReveal)
class PhoneRevealAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "viewer", "seller", "phone_number", "created_at")
    list_filter = ("created_at",)
    search_fields = ("phone_number", "viewer__email", "seller__email", "listing__name")
    raw_id_fields = ("listing", "viewer", "seller")
    readonly_fields = (
        "listing",
        "viewer",
        "seller",
        "phone_number",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ("id", "blocker", "blocked", "created_at")
    search_fields = ("blocker__email", "blocked__email")
    raw_id_fields = ("blocker", "blocked")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "reported_user",
        "reason",
        "status",
        "sla_due_at",
        "action_taken",
        "created_at",
    )
    list_filter = ("reason", "status", "action_taken")
    search_fields = ("reporter__email", "reported_user__email", "details", "resolution")
    raw_id_fields = (
        "reporter",
        "reported_user",
        "listing",
        "conversation",
        "message",
        "reviewed_by",
    )
    readonly_fields = ("reviewed_at", "resolved_at")

    actions = ["mark_reviewed", "mark_dismissed"]

    def mark_reviewed(self, request, queryset):
        from apps.trust.services import review_report

        handled = 0
        for report in queryset.filter(status="OPEN"):
            review_report(report, actor=request.user, action="review")
            handled += 1
        self.message_user(request, f"{handled} report(s) marked reviewed.")

    mark_reviewed.short_description = "Mark selected reports reviewed"

    def mark_dismissed(self, request, queryset):
        from apps.trust.services import review_report

        handled = 0
        for report in queryset.filter(status="OPEN"):
            review_report(report, actor=request.user, action="dismiss")
            handled += 1
        self.message_user(request, f"{handled} report(s) dismissed.")

    mark_dismissed.short_description = "Dismiss selected reports"
