"""Shared test helpers."""

import re
from contextlib import contextmanager
from smtplib import SMTPException

from django.core.mail.backends.base import BaseEmailBackend
from rest_framework.throttling import SimpleRateThrottle

from apps.users.sms import outbox as sms_outbox

_MISSING = object()


class FailingEmailBackend(BaseEmailBackend):
    """An SMTP outage: every send raises, like a dead mail server would."""

    def send_messages(self, email_messages):
        raise SMTPException("connection refused (test outage)")


class FailingSmsBackend:
    """An SMS provider outage: every send raises SmsError."""

    def send(self, phone_number, message):
        from apps.users.sms import SmsError

        raise SmsError("provider unavailable (test outage)")


def last_sms_code() -> str | None:
    """The OTP code from the most recent console-backend SMS, or ``None``."""
    if not sms_outbox:
        return None
    match = re.search(r"\b(\d{6})\b", sms_outbox[-1]["message"])
    return match.group(1) if match else None


@contextmanager
def throttle_rate(scope: str, rate: str):
    """Temporarily set the throttle rate for one scope.

    DRF's ``SimpleRateThrottle`` snapshots ``DEFAULT_THROTTLE_RATES`` into a
    *class attribute* at import time, so ``override_settings`` never reaches
    it — the only way to change a rate mid-test is to mutate the very dict
    the throttle reads (which is the settings dict itself).
    """
    rates = SimpleRateThrottle.THROTTLE_RATES
    previous = rates.get(scope, _MISSING)
    rates[scope] = rate
    try:
        yield
    finally:
        if previous is _MISSING:
            rates.pop(scope, None)
        else:
            rates[scope] = previous
