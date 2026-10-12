"""Pluggable SMS delivery — Phase 8 of docs/todo.md.

OTP verification is the base of trust on the Algerian market, but SMS
providers come and go (local gateways, Unifonic-style aggregators, or a
WhatsApp/Viber business API when that turns out cheaper), so the transport is
a one-method interface: swap ``SMS_BACKEND`` in the environment without
touching a line of the OTP flow.

The default is the **console backend**: it mirrors ``django.core.mail`` —
the message is logged and appended to :data:`outbox`, so a developer reads
the code out of the runserver output / test output instead of paying for a
real SMS.

Nothing in here ever raises into the request on its own: callers decide
whether a delivery failure is fatal (it never is for registration) or worth a
503 (a password reset where the user is waiting for the code).
"""

import json
import logging
import urllib.request

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger("apps.users.sms")

#: Mirror of ``django.core.mail.outbox`` for the console/test backend.
outbox: list[dict] = []


class SmsError(Exception):
    """Delivery failed (provider down, unconfigured, rejected)."""


class SmsBackend:
    """Interface every SMS transport implements."""

    def send(self, phone_number: str, message: str) -> None:
        raise NotImplementedError


class ConsoleSmsBackend(SmsBackend):
    """Development default: print the message and record it in the outbox."""

    def send(self, phone_number: str, message: str) -> None:
        outbox.append({"phone_number": phone_number, "message": message})
        logger.info("sms to=%s body=%s", phone_number, message)


class HttpJsonSmsBackend(SmsBackend):
    """Generic JSON-over-HTTP provider (``SMS_API_URL``).

    Contract: ``POST {SMS_API_URL}`` with

    * headers: ``Content-Type: application/json`` and, when ``SMS_API_KEY``
      is set, ``Authorization: Bearer <key>``
    * body: ``{"to": "+213…", "from": "MarketHub", "text": "…"}``

    Any 2xx is success. That covers most Algerian/EMEA gateways directly, or
    with a two-line adapter on their side, which is why no vendor SDK is
    hard-wired here.
    """

    def send(self, phone_number: str, message: str) -> None:
        url = settings.SMS_API_URL
        if not url:
            raise SmsError("SMS_API_URL is not configured")

        headers = {"Content-Type": "application/json"}
        if settings.SMS_API_KEY:
            headers["Authorization"] = f"Bearer {settings.SMS_API_KEY}"
        payload = json.dumps(
            {"to": phone_number, "from": settings.SMS_FROM, "text": message}
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=settings.SMS_TIMEOUT) as response:
                if response.status >= 400:
                    raise SmsError(f"provider answered HTTP {response.status}")
        except SmsError:
            raise
        except Exception as exc:  # any transport failure becomes SmsError
            raise SmsError(f"provider request failed: {exc}") from exc


def get_sms_backend() -> SmsBackend:
    """Instantiate the transport named by ``SMS_BACKEND``."""
    return import_string(settings.SMS_BACKEND)()


def send_sms(phone_number: str, message: str) -> None:
    """Deliver one message. Raises :class:`SmsError` on failure."""
    get_sms_backend().send(phone_number, message)
