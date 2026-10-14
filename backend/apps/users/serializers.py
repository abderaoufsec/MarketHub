from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.geography.models import Commune, Wilaya
from apps.geography.serializers import CommuneSerializer, WilayaSerializer

from .models import Address, User
from .otp import OtpError, verify_otp
from .phones import normalize_phone

# Purposes an anonymous caller may request a code for. ``phone_change`` (bind
# a number to an existing account) is only reachable by an authenticated
# user; the view fixes that purpose itself and rejects it for anon callers.
ANONYMOUS_OTP_PURPOSES = ("register", "login", "password_reset")
ALL_OTP_PURPOSES = (*ANONYMOUS_OTP_PURPOSES, "phone_change")


def normalize_or_none(value) -> str | None:
    """E.164-normalize an optional phone number; ``None`` for "not given"."""
    if value is None or str(value).strip() == "":
        return None
    return normalize_phone(value)  # raises django ValidationError on junk


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""

    phone_verified = serializers.BooleanField(read_only=True)
    # Declared explicitly so the model's E.164 RegexValidator does not run
    # *before* validate_phone_number gets the chance to normalize the input
    # (the validator only accepts already-normalized values).
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "phone_verified",
            "preferred_language",
            "is_seller",
            "is_verified",
            "date_joined",
        ]
        # is_seller is read-only: a profile update must never be able to grant
        # the seller role (privilege escalation, Phase 7). Sellers opt in at
        # registration ("I want to sell") or later via a dedicated flow.
        read_only_fields = [
            "id",
            "phone_verified",
            "is_seller",
            "is_verified",
            "date_joined",
        ]

    def validate_phone_number(self, value):
        """Phase 8: every stored number is E.164 (§0.3 #7 free-text fix).

        Blank means "clear the number" and stays blank; anything else must be
        a real number — a wrong-format profile number is a 400, never junk in
        the identity column. A number already **verified** on another account
        is refused here too, so the partial unique constraint below can never
        surface as an IntegrityError 500.
        """
        if value in ("", None):
            return value
        try:
            normalized = normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

        holders = User.objects.filter(phone_number=normalized, phone_verified_at__isnull=False)
        if self.instance is not None:
            holders = holders.exclude(pk=self.instance.pk)
        if holders.exists():
            raise serializers.ValidationError(
                "This phone number is already verified on another account."
            )
        return normalized

    def update(self, instance, validated_data):
        """Changing the number on a profile invalidates its old proof: the
        replacement is stored unverified until its own OTP confirms it."""
        if "phone_number" in validated_data:
            new_phone = validated_data["phone_number"] or None
            if new_phone != instance.phone_number:
                validated_data["phone_verified_at"] = None
        return super().update(instance, validated_data)


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration.

    Phase 8: **phone-first sign-up**. Email is optional — in Algeria most
    buyers have no usable inbox — and a phone number may be supplied with the
    OTP that proved ownership (``otp_code``) so the account can log in with
    neither an email link nor a second step later.
    """

    email = serializers.EmailField(required=False, allow_blank=True, default="")
    username = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")
    otp_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "otp_code",
            "preferred_language",
            "is_seller",
        ]

    def validate(self, attrs):
        # 1. Cheap checks first — a password typo must not burn the OTP.
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        email = str(attrs.get("email") or "").strip() or None
        attrs["email"] = email

        try:
            phone = normalize_or_none(attrs.get("phone_number"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"phone_number": exc.messages}) from exc
        attrs["phone_number"] = phone

        if not email and not phone:
            raise serializers.ValidationError(
                {"email": ["Enter an email address or a phone number to sign up."]}
            )

        if email and User.objects.filter(email=email).exists():
            # Keeps the field-level shape the API contract already returns.
            raise serializers.ValidationError(
                {"email": ["An account with this email address already exists."]}
            )

        otp_code = str(attrs.get("otp_code") or "").strip()
        attrs["otp_code"] = otp_code

        if phone:
            # Claiming an already-verified number must fail *before* the code
            # is consumed, so the response is honest and the budget unspent.
            if User.objects.filter(phone_number=phone, phone_verified_at__isnull=False).exists():
                raise serializers.ValidationError(
                    {"phone_number": ["This phone number is already registered."]}
                )
            # Phone-only accounts have no email link to verify with: proving
            # the number is then mandatory, otherwise the account could never
            # log in (login requires a verified identity).
            if not email and not otp_code:
                raise serializers.ValidationError(
                    {"otp_code": ["Enter the code we sent by SMS to activate this account."]}
                )

        # 2. Last: the OTP is single-use, so it is consumed only once
        #    everything else about the request is valid.
        attrs["phone_verified_now"] = False
        if phone and otp_code:
            try:
                verify_otp(phone_number=phone, purpose="register", code=otp_code)
            except (OtpError, DjangoValidationError) as exc:
                message = exc.messages if isinstance(exc, DjangoValidationError) else [str(exc)]
                raise serializers.ValidationError({"otp_code": message}) from exc
            attrs["phone_verified_now"] = True

        if not str(attrs.get("username") or "").strip():
            attrs["username"] = self._derive_username(email, phone)
        attrs["username"] = self._unique_username(attrs["username"])
        return attrs

    @staticmethod
    def _derive_username(email, phone) -> str:
        if email:
            return email.split("@", 1)[0][:140]
        digits = (phone or "").lstrip("+")
        return f"user{digits[-8:]}"

    @staticmethod
    def _unique_username(base: str) -> str:
        candidate = base or "user"
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate[:150]

    def create(self, validated_data):
        validated_data.pop("password_confirm", None)
        validated_data.pop("otp_code", None)  # consumed in validate(), never stored
        phone_verified_now = validated_data.pop("phone_verified_now", False)
        phone = validated_data.get("phone_number") or None

        user = User.objects.create_user(
            email=validated_data.get("email") or None,
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone_number=phone,
            is_seller=validated_data.get("is_seller", False),
            # Phase 11: someone signing up from the Arabic UI gets Arabic
            # emails/SMS without a second step.
            preferred_language=validated_data.get("preferred_language") or "fr",
        )
        if phone and phone_verified_now:
            # The OTP in this request already proved ownership of the number.
            User.objects.filter(pk=user.pk).update(phone_verified_at=timezone.now())
            user.phone_verified_at = timezone.now()
        return user


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change (authenticated)"""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    """Request a password-reset email. Enumeration-safe: the view answers the
    same way whether or not the address exists."""

    email = serializers.EmailField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    """Consume the emailed ``uid``/``token`` pair and set a new password."""

    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs


class ResendVerificationSerializer(serializers.Serializer):
    """Ask for another email-verification link (same non-enumerating reply)."""

    email = serializers.EmailField(required=True)


class PhoneOtpRequestSerializer(serializers.Serializer):
    """``POST /api/auth/phone/otp/`` — send a code to a number."""

    phone_number = serializers.CharField(required=True)
    purpose = serializers.ChoiceField(
        choices=[(p, p) for p in ALL_OTP_PURPOSES],
        required=False,
        default="register",
    )

    def validate_phone_number(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class PhoneLoginSerializer(serializers.Serializer):
    """Passwordless sign-in: the latest code for this number is the credential."""

    phone_number = serializers.CharField(required=True)
    code = serializers.CharField(required=True)

    def validate_phone_number(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class PhonePasswordResetSerializer(serializers.Serializer):
    """Recover access **by phone** — the path a phone-only user needs."""

    phone_number = serializers.CharField(required=True)
    code = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs

    def validate_phone_number(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class PhoneVerifySerializer(serializers.Serializer):
    """Authenticated: attach + verify a phone number on your own account."""

    phone_number = serializers.CharField(required=True)
    code = serializers.CharField(required=True)

    def validate_phone_number(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class SocialLoginSerializer(serializers.Serializer):
    """``POST /api/auth/social/`` — provider token, verified server-side."""

    provider = serializers.ChoiceField(choices=["google", "facebook"])
    access_token = serializers.CharField(required=True)


class AddressSerializer(serializers.ModelSerializer):
    """Address payload (Phase 11): reads nested geography, writes ids.

    Clients send ``wilaya_id`` (required) and ``commune_id`` (optional, but it
    must belong to that wilaya — a mismatch is a client bug, not something to
    silently repair). Responses nest the full ``wilaya``/``commune`` objects so
    a list of addresses renders without extra calls. ``country`` is derived:
    every wilaya is Algerian, so it is read-only and defaults to "DZ".
    """

    wilaya = WilayaSerializer(read_only=True)
    commune = CommuneSerializer(read_only=True)
    wilaya_id = serializers.IntegerField(write_only=True, required=True)
    commune_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Address
        fields = [
            "id",
            "address_line1",
            "address_line2",
            "wilaya",
            "commune",
            "wilaya_id",
            "commune_id",
            "country",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "country", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        wilaya_id = attrs.get("wilaya_id")
        if wilaya_id is None and self.instance is not None:
            wilaya_id = self.instance.wilaya_id
        wilaya = Wilaya.objects.filter(id=wilaya_id, is_active=True).first()
        if wilaya is None:
            raise serializers.ValidationError({"wilaya_id": _("Wilaya not found.")})

        commune_id = attrs.get("commune_id")
        commune = None
        if commune_id not in (None, ""):
            commune = Commune.objects.filter(id=commune_id, wilaya=wilaya, is_active=True).first()
            if commune is None:
                raise serializers.ValidationError(
                    {"commune_id": _("Commune not found in this wilaya.")}
                )

        # Resolve to model instances and drop the write-only id keys, so
        # create()/update() receive each foreign key exactly once.
        attrs.pop("wilaya_id", None)
        attrs.pop("commune_id", None)
        attrs["wilaya"] = wilaya
        attrs["commune"] = commune
        return attrs
