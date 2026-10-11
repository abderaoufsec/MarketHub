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
    """Best-effort write of one audit row (never raises)."""
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:256] if request else ""
    try:
        AuthEvent.objects.create(
            user=user,
            event=event,
            email=email or (user.email if user else ""),
            ip=client_ip(request) if request else None,
            user_agent=user_agent,
            details=details or {},
        )
    except Exception:
        logger.exception("auth audit write failed (event=%s)", event)
    logger.info(
        "auth_event event=%s email=%s user_id=%s ip=%s",
        event,
        email or (user.email if user else ""),
        user.pk if user else None,
        client_ip(request) if request else None,
    )
