"""Delivery channels for saved-search alerts (Phase 15).

Three transports, one tiny interface each:

* **email** - Django's configured email backend (console in dev/tests);
* **SMS** - the Phase 8 ``apps.users.sms`` transport, reused as-is;
* **WhatsApp** - a mirror of the SMS transport (``WHATSAPP_BACKEND``), with a
  console default so dev and tests never call a business API.

A channel failure is logged and swallowed by the caller: a saved-search alert
is a convenience, and an unreachable SMS gateway must never turn "publish"
into a 500 for the seller.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string

from apps.users.sms import send_sms

logger = logging.getLogger("apps.search.notifications")

#: Mirror of ``django.core.mail.outbox`` for the console WhatsApp backend.
whatsapp_outbox: list[dict] = []


class WhatsAppError(Exception):
    """Delivery failed (provider down, unconfigured, rejected)."""


class AlertDeliveryError(Exception):
    """One or more channels failed; the others were still attempted."""


class WhatsAppBackend:
    def send(self, phone_number: str, message: str) -> None:
        raise NotImplementedError


class ConsoleWhatsAppBackend(WhatsAppBackend):
    """Development default: log + record, exactly like the SMS console."""

    def send(self, phone_number: str, message: str) -> None:
        whatsapp_outbox.append({"phone_number": phone_number, "message": message})
        logger.info("whatsapp to=%s body=%s", phone_number, message)


class HttpJsonWhatsAppBackend(WhatsAppBackend):
    """Generic JSON-over-HTTP provider (``WHATSAPP_API_URL``).

    The contract is deliberately the SMS one (``to``/``from``/``text``) so a
    local gateway or a Business API adapter can sit behind it unchanged.
    """

    def send(self, phone_number: str, message: str) -> None:
        url = settings.WHATSAPP_API_URL
        if not url:
            raise WhatsAppError("WHATSAPP_API_URL is not configured")
        headers = {"Content-Type": "application/json"}
        if settings.WHATSAPP_API_KEY:
            headers["Authorization"] = f"Bearer {settings.WHATSAPP_API_KEY}"
        payload = json.dumps(
            {"to": phone_number, "from": settings.WHATSAPP_FROM, "text": message}
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=settings.WHATSAPP_TIMEOUT) as response:
                if response.status >= 400:
                    raise WhatsAppError(f"provider answered HTTP {response.status}")
        except WhatsAppError:
            raise
        except Exception as exc:
            raise WhatsAppError(f"provider request failed: {exc}") from exc


def send_whatsapp(phone_number: str, message: str) -> None:
    backend = import_string(
        getattr(settings, "WHATSAPP_BACKEND", "apps.search.notifications.ConsoleWhatsAppBackend")
    )()
    backend.send(phone_number, message)


def listing_url(product) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}{product.canonical_path}"


def alert_subject(saved_search, count: int) -> str:
    label = saved_search.name or saved_search.params.get("q") or "your saved search"
    return f"MarketHub - {count} new listing(s) for {label}"


def alert_body(saved_search, products) -> str:
    lines = [alert_subject(saved_search, len(products)), ""]
    for product in products[:5]:
        lines.append(f"- {product.name}: {listing_url(product)}")
    if len(products) > 5:
        lines.append(f"...and {len(products) - 5} more")
    lines.append("")
    lines.append("Manage your alerts in your MarketHub account.")
    return "\n".join(lines)


def short_alert(saved_search, products) -> str:
    first = products[0].name if products else ""
    label = saved_search.name or saved_search.params.get("q") or "MarketHub"
    more = f" (+{len(products) - 1} more)" if len(products) > 1 else ""
    return f"{label}: {first}{more} {listing_url(products[0]) if products else ''}".strip()[:320]


def deliver(saved_search, products) -> None:
    """Send one alert on every channel the saved search enabled.

    Each transport is attempted independently: an SMS failure must not stop
    the email. A failure is logged here and re-raised once at the end as
    ``AlertDeliveryError`` so the daily report can count it; the caller
    (``alerts``) already guarantees publishing cannot fail because of it.
    """
    if not products:
        return
    user = saved_search.user
    failures: list[str] = []

    def attempt(channel: str, send) -> None:
        try:
            send()
        except Exception:
            logger.exception("%s alert for saved search %s failed", channel, saved_search.pk)
            failures.append(channel)

    if saved_search.notify_email and user.email:
        attempt(
            "email",
            lambda: send_mail(
                alert_subject(saved_search, len(products)),
                alert_body(saved_search, products),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            ),
        )
    text = short_alert(saved_search, products)
    if saved_search.notify_sms and user.phone_number:
        attempt("sms", lambda: send_sms(user.phone_number, text))
    if saved_search.notify_whatsapp and user.phone_number:
        attempt("whatsapp", lambda: send_whatsapp(user.phone_number, text))
    if failures:
        raise AlertDeliveryError(", ".join(failures))
