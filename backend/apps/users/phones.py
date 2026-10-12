"""Phone number normalization — Phase 8 of docs/todo.md.

In Algeria the phone number, not the email address, is the primary identity
(most buyers have no usable inbox, and every Ouedkniss-style contact happens
over the number). That only works if one human number always maps to **one**
stored value, so every phone number that enters the system is normalized to
E.164 (``+213…``) here — registration, profile updates and OTP requests all go
through :func:`normalize_phone`, which is what makes the "one verified number
per account" constraint meaningful.

Accepted inputs (what people actually type):

* ``+213 555 12 34 56`` / ``00213555123456`` → already international
* ``0555123456`` → Algerian national format (trunk ``0`` swapped for ``+213``)
* ``555123456`` → Algerian significant number (no trunk prefix)
* ``213555123456`` → country code without the ``+``

Anything else raises ``django.core.exceptions.ValidationError`` so the caller
can render a 400 instead of storing junk.
"""

import re

from django.core.exceptions import ValidationError

ALGERIA_COUNTRY_CODE = "213"

# E.164 numbers top out at 15 digits; below 10 the "number" is almost always
# a typo or a partial paste.
MIN_DIGITS = 10
MAX_DIGITS = 15

_SEPARATORS = re.compile(r"[\s().\-\u200e\u200f]")


def normalize_phone(value) -> str:
    """Return ``value`` as an E.164 string, or raise ``ValidationError``."""
    if value is None:
        raise ValidationError("Enter a valid phone number.")

    raw = _SEPARATORS.sub("", str(value)).strip()
    if not raw:
        raise ValidationError("Enter a valid phone number.")

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise ValidationError("Enter a valid phone number.")

    if raw.startswith("+"):
        candidate = "+" + digits
    elif raw.startswith("00"):
        # International dialing prefix ("00213…").
        candidate = "+" + digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        # Algerian national format: 0XX XX XX XX → +213XX XX XX XX.
        candidate = f"+{ALGERIA_COUNTRY_CODE}{digits[1:]}"
    elif digits.startswith(ALGERIA_COUNTRY_CODE) and len(digits) in (12, 13):
        # Country code typed without a "+".
        candidate = "+" + digits
    elif len(digits) == 9:
        # Algerian significant number (no trunk prefix): XX XX XX XX.
        candidate = f"+{ALGERIA_COUNTRY_CODE}{digits}"
    elif len(digits) >= MIN_DIGITS:
        # Some other country's number typed as bare digits.
        candidate = "+" + digits
    else:
        raise ValidationError("Enter a valid phone number.")

    body = candidate[1:]
    if len(body) < MIN_DIGITS or len(body) > MAX_DIGITS or body[0] == "0":
        raise ValidationError("Enter a valid phone number.")
    return candidate


def is_phone_like(value) -> bool:
    """Cheap "should this string be treated as a phone number?" test.

    Used by the login form: the same field accepts an email address *or* a
    number, so the backend has to know which credential it is holding.
    """
    if not value:
        return False
    raw = _SEPARATORS.sub("", str(value))
    return bool(re.fullmatch(r"\+?\d{7,15}", raw)) and "@" not in str(value)


def mask_phone(value) -> str:
    """``+213555123456`` → ``+213••••••456`` — safe for logs and audit rows."""
    try:
        normalized = normalize_phone(value)
    except ValidationError:
        return "•" * len(str(value or ""))
    visible_head = normalized[:4]
    visible_tail = normalized[-2:]
    return f"{visible_head}{'•' * max(len(normalized) - 6, 1)}{visible_tail}"
