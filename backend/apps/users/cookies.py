"""HttpOnly cookie plumbing for the JWT session (Phase 7).

The web frontend never sees a token: the access and refresh JWTs live in
HttpOnly cookies, and a separate non-secret ``mh_session`` flag tells the UI
whether it is worth attempting a session restore (the tokens themselves are
unreadable by design).
"""

from django.conf import settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
# Readable by JS on purpose: contains no secret, only "a session probably
# exists". It lets the frontend skip pointless /profile probes for anonymous
# visitors, mirroring the pre-Phase-7 behaviour.
SESSION_HINT_COOKIE = "mh_session"

# The refresh cookie is only ever sent to the auth endpoints that need it.
REFRESH_COOKIE_PATH = "/api/auth"


def _cookie_kwargs(max_age: int) -> dict:
    return {
        "max_age": max_age,
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }


def set_auth_cookies(response, access_token, refresh_token) -> None:
    """Attach the JWT pair (HttpOnly) plus the readable session hint."""
    access_lifetime = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    refresh_lifetime = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

    response.set_cookie(
        ACCESS_COOKIE, str(access_token), path="/", **_cookie_kwargs(access_lifetime)
    )
    response.set_cookie(
        REFRESH_COOKIE,
        str(refresh_token),
        path=REFRESH_COOKIE_PATH,
        **_cookie_kwargs(refresh_lifetime),
    )
    # The hint is deliberately NOT HttpOnly: the frontend reads it.
    response.set_cookie(
        SESSION_HINT_COOKIE,
        "1",
        max_age=refresh_lifetime,
        httponly=False,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


def clear_auth_cookies(response) -> None:
    """Remove every cookie set above (paths must match to actually delete)."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(SESSION_HINT_COOKIE, path="/")
