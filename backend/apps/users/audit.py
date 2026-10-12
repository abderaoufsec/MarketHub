"""Auth audit logging helper (Phase 7 of docs/todo.md).

Writes an :class:`~apps.users.models.AuthEvent` row and a structured log line.
An audit failure must never break the request it is describing, so database
errors are swallowed into the log (the log line still goes out).
"""

import logging

from .models import AuthEvent
from .security import client_ip

logger = logging.getLogger("apps.users.auth")


def record_auth_event(request, event, *, user=None, email="", **details) -> None:
    """Best-effort write of one audit row (never raises).

    ``email`` may legitimately be ``None`` for phone-only accounts (Phase 8),
    so the stored column always falls back to ``""`` (it is NOT NULL).
    """
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:256] if request else ""
    stored_email = email or (user.email if user else "") or ""
    try:
        AuthEvent.objects.create(
            user=user,
            event=event,
            email=stored_email,
            ip=client_ip(request) if request else None,
            user_agent=user_agent,
            details=details or {},
        )
    except Exception:
        logger.exception("auth audit write failed (event=%s)", event)
    logger.info(
        "auth_event event=%s email=%s user_id=%s ip=%s",
        event,
        stored_email,
        user.pk if user else None,
        client_ip(request) if request else None,
    )
