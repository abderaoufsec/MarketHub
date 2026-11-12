"""Cheap, explainable message safety checks (Phase 16).

The rules are deliberately conservative and only *block* on the very first
message. Later messages can mention a phone number in a legitimate negotiation;
they carry a warning flag instead. The UI turns the flag into a nudge, and a
report stores it for review.
"""

from __future__ import annotations

import re

#: A phone-like run: at least nine digits once separators are stripped.
_PHONE_CANDIDATE = re.compile(r"\+?[0-9][0-9\s().-]{7,}[0-9]")
_DIGITS = re.compile(r"\D")

#: Explicit URLs, www hosts, and common TLD-shaped links without a scheme.
_URL = re.compile(
    r"""(?ix)
    (?:https?://|www\.)\S+
    |
    \b[a-z0-9][a-z0-9.-]*\.(?:com|net|org|dz|io|ly|me|co|link|site)\b
    """,
)

_OFF_PLATFORM = (
    "western union",
    "moneygram",
    "bank transfer",
    "wire transfer",
    "advance payment",
    "pay in advance",
    "pay first",
    "send money",
    "virement",
    "paiement a l'avance",
    "paiement à l'avance",
    "payer d'abord",
    "تحويل",
    "دفع مسبق",
    "ادفع أولا",
    "ادفع أولاً",
)


def _looks_like_phone(candidate: str) -> bool:
    digits = _DIGITS.sub("", candidate)
    return 9 <= len(digits) <= 15


def first_message_violations(body: str) -> list[str]:
    """Reasons the first message must be rejected, in stable order."""
    reasons: list[str] = []
    if any(_looks_like_phone(match.group(0)) for match in _PHONE_CANDIDATE.finditer(body)):
        reasons.append("phone_number")
    if _URL.search(body):
        reasons.append("link")
    return reasons


def safety_flags(body: str) -> list[str]:
    """Nudges shown under a message. Never blocks on its own."""
    flags: list[str] = []
    if any(_looks_like_phone(match.group(0)) for match in _PHONE_CANDIDATE.finditer(body)):
        flags.append("phone_number")
    if _URL.search(body):
        flags.append("suspicious_link")
    lowered = body.casefold()
    if any(phrase in lowered for phrase in _OFF_PLATFORM):
        flags.append("off_platform_payment")
    return flags
