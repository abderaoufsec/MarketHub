"""Phone OTP issuing and verification — Phase 8 of docs/todo.md.

The code that decides whether a +213 number belongs to the person holding the
form. Three properties matter, in order:

1. **It must be hard to guess** — a ``OTP_LENGTH``-digit code from
   :mod:`secrets`, stored only as a SHA-256 hash, checked in constant time,
   and capped at ``OTP_MAX_ATTEMPTS`` wrong tries per code (1e6 codes is a
   lot; 1e6 *attempts* is not if each one is a request).
2. **It must expire** — ``OTP_TTL_SECONDS`` (default 5 minutes), single use.
3. **It must be expensive to pump** — an attacker who feeds numbers into the
   request endpoint pays for every SMS. Cooldown between sends plus
   per-number and per-IP daily budgets (cache counters, like
   ``security.py``'s login backoff) keep a pumping run bounded.

The transport is pluggable (``sms.py``): swap ``SMS_BACKEND`` for a local
gateway or a WhatsApp/Viber business API without touching this module.
"""

import hashlib
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import Throttled

from .models import PhoneOtp, User
from .phones import normalize_phone
from .sms import SmsError, send_sms

DAY = 86400


class OtpError(Exception):
    """Wrong/expired/missing code. Message is safe to show the caller."""


def generate_code() -> str:
    """A cryptographically random, zero-padded code (``secrets``, not ``random``)."""
    span = 10**settings.OTP_LENGTH
    return f"{secrets.randbelow(span):0{settings.OTP_LENGTH}d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _cooldown_key(phone: str, purpose: str) -> str:
    return f"otp:cooldown:{purpose}:{phone}"


def _phone_day_key(phone: str) -> str:
    return f"otp:day:phone:{phone}"


def _ip_day_key(ip: str) -> str:
    return f"otp:day:ip:{ip}"


def _bump(key: str, ttl: int = DAY) -> int:
    """Increment a counter, setting its TTL on first use.

    The TTL is per-counter on purpose: the resend cooldown expires after
    ``OTP_RESEND_COOLDOWN_SECONDS`` while the daily budgets live for a day.
    """
    # LocMem cache has no atomic add_or_incr across backends worth relying on
    # here; a race only ever loses one count, and the DRF throttle on the
    # request endpoint is the second line of defence.
    value = int(cache.get(key) or 0) + 1
    cache.set(key, value, timeout=ttl)
    return value


def enforce_request_budget(*, phone: str, purpose: str, ip: str | None) -> None:
    """Raise ``Throttled`` (HTTP 429) when an OTP request would break a budget.

    Checked *before* any message is sent so a pumping run never pays for the
    request that trips the limit.
    """
    if cache.get(_cooldown_key(phone, purpose)):
        raise Throttled(detail="A code was just sent. Wait a moment before requesting another.")

    sent_to_number = int(cache.get(_phone_day_key(phone)) or 0)
    if sent_to_number >= settings.OTP_MAX_PER_PHONE_PER_DAY:
        raise Throttled(detail="Daily limit reached for this phone number. Try again tomorrow.")

    if ip:
        sent_from_ip = int(cache.get(_ip_day_key(ip)) or 0)
        if sent_from_ip >= settings.OTP_MAX_PER_IP_PER_DAY:
            raise Throttled(detail="Daily limit reached from this address. Try again later.")


def issue_otp(
    *,
    phone_number: str,
    purpose: str,
    user: User | None = None,
    ip: str | None = None,
) -> PhoneOtp:
    """Create, persist (hashed) and deliver one code.

    Raises ``ValidationError`` for a malformed number, ``Throttled`` when a
    budget is spent, and ``SmsError`` when the transport fails — in which case
    **no row survives**, so a user never holds a code the backend does not
    know about.
    """
    phone = normalize_phone(phone_number)
    enforce_request_budget(phone=phone, purpose=purpose, ip=ip)

    code = generate_code()
    now = timezone.now()
    with transaction.atomic():
        # A new code invalidates the outstanding one for the same target:
        # only the latest message can ever work.
        PhoneOtp.objects.filter(
            phone_number=phone, purpose=purpose, consumed_at__isnull=True
        ).update(consumed_at=now)

        row = PhoneOtp.objects.create(
            user=user,
            phone_number=phone,
            purpose=purpose,
            code_hash=hash_code(code),
            expires_at=now + timezone.timedelta(seconds=settings.OTP_TTL_SECONDS),
            ip=ip,
        )

        try:
            send_sms(
                phone,
                f"Your MarketHub code is {code}. It expires in "
                f"{settings.OTP_TTL_SECONDS // 60} minutes. Never share it.",
            )
        except SmsError:
            # Delivery failed → the code can never be entered. Do not leave a
            # live row (or a spent budget) behind for a message nobody got.
            row.delete()
            raise

    _bump(_cooldown_key(phone, purpose), settings.OTP_RESEND_COOLDOWN_SECONDS)
    # Both daily counters start once the message is actually on its way —
    # a failed send (raised above, row already rolled back) costs nothing.
    _bump(_phone_day_key(phone))
    if ip:
        _bump(_ip_day_key(ip))
    return row


def verify_otp(*, phone_number: str, purpose: str, code: str) -> PhoneOtp:
    """Consume the latest usable code for (phone, purpose) or raise ``OtpError``.

    Wrong codes burn an attempt *before* the next guess is possible; the
    attempt cap and the expiry end the guessing window entirely. On success
    the row is marked consumed (single use) and returned so the caller can
    act on ``row.user`` / ``row.phone_number``.
    """
    phone = normalize_phone(phone_number)
    row = (
        PhoneOtp.objects.filter(phone_number=phone, purpose=purpose).order_by("-created_at").first()
    )
    if row is None or not row.is_usable:
        raise OtpError("Invalid or expired code.")

    if not secrets.compare_digest(row.code_hash, hash_code(str(code or ""))):
        row.attempts += 1
        row.save(update_fields=["attempts"])
        if not row.is_usable:
            raise OtpError("Invalid or expired code.")
        raise OtpError("Invalid code.")

    row.consumed_at = timezone.now()
    row.save(update_fields=["consumed_at"])
    return row


def clear_budgets(*, phone: str) -> None:
    """Wipe the send budgets for a number (used after a successful claim so a
    legitimate user who just verified is not still counting against the cap)."""
    cache.delete(_phone_day_key(phone))
