"""The API's error catalogue must stay in step with the code that raises it.

Three things can rot independently, so each is asserted here:

1. A ``.po`` edited without recompiling — caught by comparing the committed
   ``.mo`` byte-for-byte against a fresh compile (the project compiles with
   :mod:`core.mofile` because GNU ``msgfmt`` is not assumed to exist, so this
   *is* the compiler check).
2. A new error message with no translation — every literal message raised by
   the backend must be a msgid in every catalogue, gathered by walking the
   AST rather than by trusting a hand-written list.
3. A translation that is just the English string pasted back in — each
   msgid must differ from its ``fr`` and ``ar`` renderings, which is what
   stops a catalogue from decaying into a mirror.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.utils.translation import gettext, override

from core.mofile import build_mo, iter_catalogues, parse_po

BACKEND = Path(__file__).resolve().parents[1]
LANGUAGES = ("fr", "ar")

#: Exception constructors whose first *positional* argument is a sentence a
#: user will read. Includes the domain families that subclass ``ApiError``
#: (``OrderDomainError``, ``PaymentError``, …) and the transport ones
#: (``NotFound``, ``PermissionDenied``) so a new failure mode is caught the
#: day it is written, not the day someone notices the docs are stale.
MESSAGE_TAKING_CALLS = frozenset(
    {
        "ApiError",
        "InternalServerError",
        "OtpError",
        "SocialError",
        "SmsError",
        "NotFound",
        "PermissionDenied",
        "ValidationError",
        "OrderDomainError",
        "PaymentError",
        "ProductUnavailableError",
        "PriceChangedError",
        "ShippingAddressNotFoundError",
        "EmptyCartError",
        "InsufficientStockError",
        "PaymentFailedError",
        "OrderNotFoundError",
        "OrderAlreadyPaidError",
        "OrderNotPayableError",
        "PaymentCaptureFailedError",
        "RefundNotPaidError",
        "RefundAlreadyDeliveredError",
        "RefundNoTransactionError",
        "RefundFailedError",
    }
)


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _first_string_argument(node: ast.Call) -> str | None:
    """The first positional argument, but only if it is a plain literal.

    An f-string or a ``str(exc)`` is deliberately skipped: gettext matches on
    the exact text, so a message that interpolates can never be looked up
    under one msgid anyway. Those messages are translated by construction
    elsewhere (or not at all), and the catalogue must not pretend otherwise.
    """
    if not node.args:
        return None
    argument = node.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        value = argument.value
        return value if value.strip() else None
    return None


def _raised_messages() -> set[str]:
    """Every literal error message the backend can put in the envelope."""
    messages: set[str] = set()
    roots = [BACKEND / "core", BACKEND / "apps"]
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "migrations" in path.parts or "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if _called_name(node) not in MESSAGE_TAKING_CALLS:
                    continue
                text = _first_string_argument(node)
                if text:
                    messages.add(text)
    return messages


@pytest.fixture(scope="module")
def catalogues() -> dict[str, dict[str, str]]:
    loaded = {}
    for po_path, _mo_path in iter_catalogues(settings.LOCALE_PATHS):
        language = po_path.parent.parent.name
        loaded[language] = parse_po(po_path.read_text(encoding="utf-8"), where=str(po_path))
    return loaded


def test_every_language_has_a_catalogue(catalogues):
    assert sorted(catalogues) == sorted(LANGUAGES)


def test_catalogues_carry_a_utf8_header(catalogues):
    for language, entries in catalogues.items():
        assert entries.get(""), f"{language}: missing the empty-msgid header"
        assert "charset=UTF-8" in entries[""], (
            f"{language}: header does not declare UTF-8, so gettext would "
            "decode the rest as ASCII and mangle every translation"
        )


def test_committed_mo_files_are_recompiled(catalogues):
    """``.po`` edited, ``.mo`` forgotten — the failure nobody notices until
    production answers in English."""
    stale = []
    for po_path, mo_path in iter_catalogues(settings.LOCALE_PATHS):
        entries = parse_po(po_path.read_text(encoding="utf-8"), where=str(po_path))
        if not mo_path.exists() or mo_path.read_bytes() != build_mo(entries):
            stale.append(mo_path.relative_to(BACKEND).as_posix())
    assert not stale, (
        f"{stale} out of date — run `python manage.py compile_api_messages` "
        "and commit the .mo files"
    )


def test_every_raised_message_is_translated(catalogues):
    """The ratchet: a new error cannot ship English-only to fr/ar."""
    raised = _raised_messages()
    assert raised, "extraction found no messages — the walk is broken"

    for language, entries in catalogues.items():
        missing = sorted(message for message in raised if message not in entries)
        assert not missing, (
            f"{language} catalogue is missing {len(missing)} message(s) raised "
            f"by the backend: {missing}"
        )


def test_translations_are_actually_translated(catalogues):
    """A copy of the English is worse than no entry: it looks covered."""
    identical = {
        language: sorted(
            message
            for message, translated in entries.items()
            if message
            and translated == message
            and not message.startswith(("SMS_API_", "order_id", "product_id"))
        )
        for language, entries in catalogues.items()
    }
    for language, messages in identical.items():
        assert not messages, f"{language}: untranslated copies of English: {messages}"


def test_the_handler_speaks_the_requested_language(catalogues):
    """End to end through the *envelope*, not through ``gettext`` directly —
    the point is what a client reads off a 400."""
    from core.exceptions import build_error_body

    rendered = {}
    for language in ("en", *LANGUAGES):
        with override(language):
            rendered[language] = build_error_body(
                code="validation_error",
                message=gettext("Some of the submitted values are invalid."),
                details={"email": ["This field is required."]},
                request_id="test-request-id",
            )

    assert len({body["message"] for body in rendered.values()}) == len(rendered), (
        f"envelope message did not vary by language: {rendered}"
    )
    for language in LANGUAGES:
        assert rendered[language]["code"] == "validation_error", (
            "code must not be localised — clients branch on it"
        )
