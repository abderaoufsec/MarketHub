"""Trust & safety rows (Phase 17).

The marketplace already had *reports* (Phase 16). This app adds the machinery
around them: seller identity tiers, the shared blocklist, moderation audits,
account sanctions and appeals.

Nothing here duplicates the chat tables on purpose. A report still points at
its conversation/message/listing, so the moderator keeps the original context.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class VerificationKind(models.TextChoices):
    IDENTITY = "IDENTITY", "Identity"
    STORE = "STORE", "Store"


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class SellerVerification(models.Model):
    """One identity/store verification request.

    The tier a buyer sees is *derived* from these rows (see
    :func:`apps.trust.reputation.tier_for_user`) instead of being a mutable
    flag on the user: a mistyped admin action must not be able to grant a
    badge without an approved row behind it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trust_verifications",
    )
    kind = models.CharField(max_length=16, choices=VerificationKind.choices)
    status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    #: ID card / passport / commercial register photo. ``Image`` gives us the
    #: processed, EXIF-free file and an owner check for free.
    document_image = models.ForeignKey(
        "media.Image",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_documents",
    )
    #: Selfie holding the document, only for IDENTITY.
    selfie_image = models.ForeignKey(
        "media.Image",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_selfies",
    )
    document_type = models.CharField(max_length=32, blank=True, default="")
    document_number = models.CharField(max_length=64, blank=True, default="")
    commercial_register_number = models.CharField(max_length=64, blank=True, default="")
    nif_number = models.CharField(max_length=64, blank=True, default="")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trust_verifications",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verifications_reviewed",
    )
    rejection_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "trust_seller_verifications"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"],
                name="unique_verification_per_user_kind",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-submitted_at"], name="trust_verif_status_recent"),
            models.Index(fields=["user", "kind"], name="trust_verif_user_kind"),
        ]

    def __str__(self):
        return f"{self.kind} verification for {self.user_id} ({self.status})"

    @property
    def is_approved(self) -> bool:
        return self.status == VerificationStatus.APPROVED


class BlocklistKind(models.TextChoices):
    PHONE = "PHONE", "Phone number"
    DEVICE = "DEVICE", "Device / fingerprint"
    IP = "IP", "IP address"
    BANK_ACCOUNT = "BANK_ACCOUNT", "Bank account / CCP"
    IMAGE_HASH = "IMAGE_HASH", "Image perceptual hash"


class BlocklistQuerySet(models.QuerySet):
    def active(self):
        now = timezone.now()
        return self.filter(is_active=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )


class BlocklistEntry(models.Model):
    """A value that may not appear on the marketplace (shared blocklist).

    Values are stored *normalized*: phones as E.164, IPs in canonical form,
    bank accounts as digits only, image hashes lowercase. Services call
    :func:`apps.trust.blocklists.normalize_value` before reading or writing,
    so the same human input always hits the same row.
    """

    kind = models.CharField(max_length=16, choices=BlocklistKind.choices)
    value = models.CharField(max_length=255)
    reason = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocklist_entries_created",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BlocklistQuerySet.as_manager()

    class Meta:
        db_table = "trust_blocklist"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "value"], name="unique_blocklist_value"),
        ]
        indexes = [
            models.Index(fields=["kind", "value"], name="trust_blocklist_lookup"),
            models.Index(fields=["is_active", "-created_at"], name="trust_blocklist_active"),
        ]

    def __str__(self):
        return f"{self.kind}: {self.value}"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())


class AuditAction(models.TextChoices):
    VERIFICATION_SUBMITTED = "VERIFICATION_SUBMITTED", "Verification submitted"
    VERIFICATION_APPROVED = "VERIFICATION_APPROVED", "Verification approved"
    VERIFICATION_REJECTED = "VERIFICATION_REJECTED", "Verification rejected"
    REPORT_REVIEWED = "REPORT_REVIEWED", "Report reviewed"
    REPORT_DISMISSED = "REPORT_DISMISSED", "Report dismissed"
    REPORT_ACTIONED = "REPORT_ACTIONED", "Report actioned"
    LISTING_REMOVED = "LISTING_REMOVED", "Listing removed"
    USER_BANNED = "USER_BANNED", "User banned"
    USER_SUSPENDED = "USER_SUSPENDED", "User suspended"
    USER_REINSTATED = "USER_REINSTATED", "User reinstated"
    APPEAL_APPROVED = "APPEAL_APPROVED", "Appeal approved"
    APPEAL_REJECTED = "APPEAL_REJECTED", "Appeal rejected"
    BLOCKLIST_ADDED = "BLOCKLIST_ADDED", "Blocklist entry added"
    BLOCKLIST_REMOVED = "BLOCKLIST_REMOVED", "Blocklist entry removed"
    MASS_ACTION = "MASS_ACTION", "Mass moderation action"


class ModerationAuditLog(models.Model):
    """Append-only who-did-what trail for every trust action.

    The admin's own Django log is not enough: this is exposed to the support
    team and survives a user being deleted (target ids are integers, not FKs).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices)
    target_type = models.CharField(max_length=32, blank=True, default="")
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "trust_audit_log"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="trust_audit_target"),
            models.Index(fields=["action", "-created_at"], name="trust_audit_action"),
        ]

    def __str__(self):
        return f"{self.action} {self.target_type}:{self.target_id}"


class SanctionKind(models.TextChoices):
    WARNING = "WARNING", "Warning"
    SUSPEND = "SUSPEND", "Suspension"
    BAN = "BAN", "Ban"


class AccountSanction(models.Model):
    """A warning/suspension/ban that can be lifted or expire.

    ``User.is_active`` remains the login gate (Django's own machinery already
    honours it); this row explains *why* and can be reversed without losing
    the history.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trust_sanctions",
    )
    kind = models.CharField(max_length=16, choices=SanctionKind.choices)
    reason = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sanctions_created",
    )
    lifted_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trust_account_sanctions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="trust_sanction_user"),
            models.Index(fields=["kind", "is_active"], name="trust_sanction_kind_active"),
        ]

    def __str__(self):
        return f"{self.kind} for {self.user_id}"

    @property
    def is_current(self) -> bool:
        if not self.is_active or self.lifted_at is not None:
            return False
        return not self.expires_at or self.expires_at > timezone.now()


class AppealKind(models.TextChoices):
    LISTING = "LISTING", "Rejected listing"
    ACCOUNT = "ACCOUNT", "Banned or suspended account"
    REVIEW = "REVIEW", "Hidden review"


class AppealStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Appeal(models.Model):
    """A user's request to restore a listing, account or review."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trust_appeals",
    )
    kind = models.CharField(max_length=16, choices=AppealKind.choices)
    listing = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals",
    )
    review = models.ForeignKey(
        "products.ProductReview",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals",
    )
    message = models.TextField()
    status = models.CharField(
        max_length=16, choices=AppealStatus.choices, default=AppealStatus.OPEN
    )
    resolution = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trust_appeals"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="trust_appeal_status"),
            models.Index(fields=["user", "-created_at"], name="trust_appeal_user"),
        ]

    def __str__(self):
        return f"Appeal {self.pk} ({self.kind}, {self.status})"
