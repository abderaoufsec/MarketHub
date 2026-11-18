"""Shared blocklist normalisation and matching (Phase 17).

The same phone number can be typed as ``0555 12 34 56``, ``+213555123456`` or
``00213555123456``. A blocklist that stores the raw string is therefore a
blocklist that is easy to evade by adding a space. Every write and every
lookup goes through :func:`normalize_value`.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.users.phones import normalize_phone

from .models import BlocklistEntry, BlocklistKind

_IP_RE = re.compile(r"^[0-9a-fA-F:.]+$")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d(?:[\d\s().-]{7,}\d)")
_BANK_HINT_RE = re.compile(r"(?i)(ccp|rib|compte|bank|banque|account|حساب|بريد|بنك)")
_DIGIT_RUN_RE = re.compile(r"\d{8,24}")
_SEPARATORS_RE = re.compile(r"[\s().\-\u200e\u200f]")


def normalize_value(kind: str, value: str) -> str:
    """Return the canonical stored form for one blocklist value.

    Unknown kinds are stored lowercased/trimmed. Invalid phones keep their
    digits, so an admin can still block a malformed-but-reported number
    instead of getting a 500 from the form.
    """
    raw = (value or "").strip()
    if kind == BlocklistKind.PHONE:
        try:
            return normalize_phone(raw)
        except ValidationError:
            return "".join(ch for ch in raw if ch.isdigit())
    if kind == BlocklistKind.IP:
        return raw.lower()
    if kind == BlocklistKind.BANK_ACCOUNT:
        return "".join(ch for ch in raw if ch.isdigit())
    if kind == BlocklistKind.IMAGE_HASH:
        return raw.lower()
    return raw.lower()


def add_entry(
    *,
    kind: str,
    value: str,
    reason: str = "",
    created_by=None,
    expires_at=None,
    metadata=None,
) -> BlocklistEntry:
    normalized = normalize_value(kind, value)
    entry, _ = BlocklistEntry.objects.update_or_create(
        kind=kind,
        value=normalized,
        defaults={
            "reason": reason,
            "created_by": created_by,
            "expires_at": expires_at,
            "metadata": metadata or {},
            "is_active": True,
        },
    )
    return entry


def is_blocklisted(kind: str, value: str) -> bool:
    if not value:
        return False
    normalized = normalize_value(kind, value)
    return BlocklistEntry.objects.active().filter(kind=kind, value=normalized).exists()


def matching_entries(kind: str, value: str):
    if not value:
        return BlocklistEntry.objects.none()
    return BlocklistEntry.objects.active().filter(kind=kind, value=normalize_value(kind, value))


def _looks_like_phone(candidate: str) -> bool:
    """A *plausible* phone, not merely a run of digits.

    ``normalize_phone`` happily turns any 10-15 digit run into an E.164 value,
    which is right for a submitted profile number and wrong for a scanner:
    a timestamp in the title (``E2E Ad 1795028006944``) or an IMEI must not
    block a legitimate listing. Only international prefixes and the shapes
    people in Algeria actually type are treated as contact details.
    """
    compact = _SEPARATORS_RE.sub("", candidate or "")
    digits = "".join(ch for ch in compact if ch.isdigit())
    if compact.startswith("+") or compact.startswith("00"):
        return 10 <= len(digits) <= 15
    if len(digits) == 10 and digits.startswith("0"):
        return True  # 0X XX XX XX XX
    if len(digits) == 9 and digits[0] in "567":
        return True  # XX XX XX XX without the trunk prefix
    return digits.startswith("213") and len(digits) in (12, 13)


def extract_contacts(text: str) -> dict[str, list[str]]:
    """Pull phones, e-mails and bank-account-looking numbers out of free text.

    Used by the pre-publish scanner. Deliberately conservative on phones: the
    candidate must look like a typed phone number *and* normalize to a real
    E.164 value, otherwise a price (``45000``) or a serial/timestamp would be
    reported as a contact.
    """
    body = text or ""
    phones: list[str] = []
    for candidate in _PHONE_RE.findall(body):
        if not _looks_like_phone(candidate):
            continue
        try:
            normalized = normalize_phone(candidate)
        except ValidationError:
            continue
        if normalized not in phones:
            phones.append(normalized)

    emails = list(dict.fromkeys(match.lower() for match in _EMAIL_RE.findall(body)))

    banks: list[str] = []
    for hint in _BANK_HINT_RE.finditer(body):
        window = body[hint.end() : hint.end() + 80]
        for account in _DIGIT_RUN_RE.findall(window):
            normalized = "".join(ch for ch in account if ch.isdigit())
            if normalized not in banks:
                banks.append(normalized)
    return {"phones": phones, "emails": emails, "bank_accounts": banks}


def blocklist_flags(text: str) -> list[dict]:
    """Every contact value in ``text`` that is currently blocklisted."""
    contacts = extract_contacts(text)
    flags: list[dict] = []
    for phone in contacts["phones"]:
        if is_blocklisted(BlocklistKind.PHONE, phone):
            flags.append({"kind": BlocklistKind.PHONE, "value": phone})
    for account in contacts["bank_accounts"]:
        if is_blocklisted(BlocklistKind.BANK_ACCOUNT, account):
            flags.append({"kind": BlocklistKind.BANK_ACCOUNT, "value": account})
    return flags


def active_phone_entries():
    return BlocklistEntry.objects.active().filter(kind=BlocklistKind.PHONE)


def expire_due_entries() -> int:
    """Deactivate rows whose expiry passed; called by the admin view list."""
    return (
        BlocklistEntry.objects.active()
        .filter(expires_at__lte=timezone.now())
        .update(is_active=False)
    )
