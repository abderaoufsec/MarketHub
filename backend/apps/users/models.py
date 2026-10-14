from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(DjangoUserManager):
    """Phone-first user manager (Phase 8).

    Django's ``normalize_email`` turns ``None``/``""`` into ``""`` — fine for
    an email-only app, fatal here: the EMAIL column is UNIQUE, so the second
    phone-only account (no address) would collide with the first. An
    address-less account stores NULL instead.
    """

    @classmethod
    def normalize_email(cls, email):
        if not email:
            return None
        return super().normalize_email(email)


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    Supports both Buyer and Seller roles.

    Phase 8 — identity is **phone-first** (docs/todo.md): in Algeria the phone
    number is the primary identity, so ``email`` is now optional
    (``null=True``) and a verified phone number is an equally valid login
    credential. ``is_verified`` keeps meaning "email verified"; the phone has
    its own ``phone_verified_at`` timestamp. Either one unlocks login.

    ``phone_number`` is always stored normalized to E.164 (``+213…``) — every
    write path goes through ``apps.users.phones.normalize_phone``. Two
    accounts may *carry* the same unverified number (several sign-up attempts),
    but a **verified** number is unique across accounts
    (``unique_verified_phone_number`` below).
    """

    email = models.EmailField(_("email address"), unique=True, null=True, blank=True)
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[RegexValidator(r"^\+[1-9]\d{6,14}$", "Enter a valid E.164 phone number.")],
        help_text="Normalized to E.164 (e.g. +213555123456).",
    )
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the owner proved control of phone_number by OTP.",
    )
    is_seller = models.BooleanField(
        default=False, help_text="Designates whether this user is a seller"
    )
    is_verified = models.BooleanField(
        default=False, help_text="Designates whether email is verified"
    )
    profile_picture = models.URLField(blank=True, null=True, help_text="Profile picture URL")
    bio = models.TextField(blank=True, null=True, help_text="User biography")
    preferred_language = models.CharField(
        max_length=5,
        choices=[("ar", "العربية"), ("fr", "Français"), ("en", "English")],
        default="fr",
        blank=True,
        help_text="Language for emails, SMS and translated labels.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    # The model validators still guard full_clean()/admin, but normalization
    # happens in the serializers: input like "0555 12 34 56" must be *made*
    # valid, not rejected on its way to being made valid.
    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["phone_number"]),
            models.Index(fields=["is_seller"]),
        ]
        constraints = [
            # The *verified* number is the identity: one human, one account.
            # Unverified rows may repeat — sign-up attempts do not squat a
            # number, and OTP verification is what claims it.
            models.UniqueConstraint(
                fields=["phone_number"],
                condition=models.Q(phone_verified_at__isnull=False),
                name="unique_verified_phone_number",
            ),
        ]

    def __str__(self):
        return self.email or self.phone_number or self.username

    @property
    def phone_verified(self) -> bool:
        return self.phone_verified_at is not None

    def has_verified_identity(self) -> bool:
        """Email *or* phone proven — the gate for logging in (Phase 8)."""
        return self.is_verified or self.phone_verified


class Address(models.Model):
    """
    Model to store shipping and billing addresses for users.

    Phase 11 (docs/todo.md): the free-text ``city`` / ``state_province`` /
    ``postal_code`` trio is gone. An Algerian address is a street line plus a
    **Wilaya** and (optionally) a **Commune** — that is how the country and
    the delivery carriers index locations, and free text could never follow
    the 48 → 58 → 69 wilaya reforms. Both FKs are nullable *at the database
    level* so legacy rows survive the data migration even when their old text
    could not be matched; the API requires a wilaya on every new write.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    wilaya = models.ForeignKey(
        "geography.Wilaya",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="addresses",
    )
    commune = models.ForeignKey(
        "geography.Commune",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="addresses",
    )
    country = models.CharField(max_length=100, default="DZ", blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "addresses"
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.location_display}"

    @property
    def location_display(self) -> str:
        """Commune (wilaya), falling back gracefully for legacy rows."""
        if self.commune and self.wilaya:
            return f"{self.commune.name_fr}, {self.wilaya.name_fr}"
        if self.wilaya:
            return self.wilaya.name_fr
        return self.country

    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class PhoneOtp(models.Model):
    """One phone-verification attempt — the SMS code behind Phase 8.

    Security posture (docs/todo.md: "OTP rate limits, expiry, attempt caps"):

    * the code itself is stored **hashed** (SHA-256): a database dump must not
      hand over live login credentials;
    * ``attempts`` is capped (``OTP_MAX_ATTEMPTS``), so a 6-digit code cannot
      be sprayed;
    * one row is single-use (``consumed_at``) and short-lived
      (``expires_at``);
    * issuing a new code for the same (phone, purpose) invalidates the
      previous outstanding one;
    * per-number and per-IP daily budgets live in ``apps.users.otp`` (cache
      counters), which is what defends against SMS pumping — every sent
      message costs real money.
    """

    REGISTER = "register"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"
    PHONE_CHANGE = "phone_change"
    PURPOSE_CHOICES = [
        (REGISTER, "Sign up with this phone number"),
        (LOGIN, "Log in with this phone number"),
        (PASSWORD_RESET, "Recover access with this phone number"),
        (PHONE_CHANGE, "Verify the phone number on an existing account"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="phone_otps",
        help_text="Known at issue time for login/reset/change; null for sign-up.",
    )
    phone_number = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "phone_otps"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP {self.phone_number} ({self.purpose}) @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_usable(self) -> bool:
        return (
            not self.is_consumed
            and not self.is_expired
            and self.attempts < settings.OTP_MAX_ATTEMPTS
        )


class AuthEvent(models.Model):
    """Append-only audit trail of authentication events (Phase 7).

    Answers "who touched this account, from where, when" for incident
    response: login successes/failures, logout, password changes and resets,
    registrations, email and phone verifications.
    """

    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET = "PASSWORD_RESET"
    REGISTERED = "REGISTERED"
    EMAIL_VERIFIED = "EMAIL_VERIFIED"
    PHONE_VERIFIED = "PHONE_VERIFIED"
    EVENT_CHOICES = [
        (LOGIN_SUCCESS, "Login succeeded"),
        (LOGIN_FAILED, "Login failed"),
        (LOGOUT, "Logout"),
        (PASSWORD_CHANGED, "Password changed"),
        (PASSWORD_RESET, "Password reset"),
        (REGISTERED, "Registered"),
        (EMAIL_VERIFIED, "Email verified"),
        (PHONE_VERIFIED, "Phone verified"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_events",
        help_text="Null when the event references an unknown/failed account.",
    )
    event = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
    email = models.EmailField(blank=True, max_length=254)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "auth_events"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event} {self.email or self.user_id} @ {self.created_at:%Y-%m-%d %H:%M}"
