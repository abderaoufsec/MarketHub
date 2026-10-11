"""JWT authentication for both delivery mechanisms (Phase 7 of docs/todo.md).

1. ``Authorization: Bearer <access>`` — API / future mobile clients.
2. The ``access_token`` **HttpOnly cookie** — the web frontend. Because the
   browser attaches that cookie automatically, cookie-authenticated *unsafe*
   requests must also carry a valid CSRF token (same rule as DRF's
   ``SessionAuthentication``); otherwise a cross-site request could act as the
   logged-in user.
"""

from rest_framework import authentication, exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication

from .cookies import ACCESS_COOKIE

_SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")


def _dummy_get_response(request):  # pragma: no cover - DRF pattern, never called
    return None


class CookieJWTAuthentication(JWTAuthentication):
    """Authenticate from the Bearer header first, then from the JWT cookie."""

    def authenticate(self, request):
        if self.get_header(request) is not None:
            # Standard bearer flow: the caller proved possession of the token
            # explicitly in the request, so no CSRF check is needed.
            return super().authenticate(request)

        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        self.enforce_csrf(request)
        return (user, validated_token)

    @staticmethod
    def enforce_csrf(request):
        """Reject unsafe cookie-authenticated requests without a CSRF token."""
        if request.method in _SAFE_METHODS:
            return
        check = authentication.CSRFCheck(_dummy_get_response)
        # Populates request.META["CSRF_COOKIE"], which process_view() reads.
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason is not None:
            raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")
