"""Brute-force defences for the auth endpoints (Phase 7).

``throttles.py`` caps *request rate*; this module adds per-(IP, email)
**failed-login backoff**: after ``LOGIN_FAIL_THRESHOLD`` bad passwords the
pair is locked out with an exponentially growing window, so password spraying
slows down instead of running at full speed.

State lives in the Django cache (LocMem in dev/tests, Redis from Phase 22 on),
never in the database — a lockout must not be a durable row an attacker can
spray into existence.
"""

import time

from django.core.cache import cache
from rest_framework.exceptions import Throttled

LOGIN_FAIL_THRESHOLD = 5  # failures before the lockout kicks in
LOGIN_FAIL_WINDOW = 900  # seconds a failure stays on the record (15 min)
LOGIN_LOCKOUT_BASE = 60  # first lockout duration (1 min)
LOGIN_LOCKOUT_MAX = 900  # cap for the exponential backoff (15 min)


def client_ip(request) -> str:
    """Best-effort client IP. REMOTE_ADDR only: X-Forwarded-For is spoofable
    unless a trusted proxy is in front (Phase 28)."""
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _key(ip: str, email: str) -> str:
    return f"login-fail:{ip}:{(email or '').lower()}"


def check_login_backoff(request, email: str) -> None:
    """Raise ``Throttled`` (HTTP 429 + Retry-After) while locked out."""
    state = cache.get(_key(client_ip(request), email))
    if not state:
        return
    wait = state.get("locked_until", 0) - time.time()
    if wait > 0:
        raise Throttled(
            wait=int(wait) + 1,
            detail="Too many failed login attempts. Try again later.",
        )


def record_login_failure(request, email: str) -> None:
    """Bump the failure counter, locking out exponentially past the threshold."""
    key = _key(client_ip(request), email)
    now = time.time()
    state = cache.get(key) or {}
    # Failures older than the window no longer count.
    if state.get("window_expires", 0) < now:
        state = {}
    failures = int(state.get("failures", 0)) + 1
    locked_until = 0.0
    if failures >= LOGIN_FAIL_THRESHOLD:
        over = failures - LOGIN_FAIL_THRESHOLD
        locked_until = now + min(LOGIN_LOCKOUT_BASE * (2**over), LOGIN_LOCKOUT_MAX)
    ttl = int(LOGIN_FAIL_WINDOW + max(0.0, locked_until - now))
    cache.set(
        key,
        {
            "failures": failures,
            "window_expires": now + LOGIN_FAIL_WINDOW,
            "locked_until": locked_until,
        },
        timeout=ttl,
    )


def clear_login_failures(request, email: str) -> None:
    """Successful login wipes the record."""
    cache.delete(_key(client_ip(request), email))
