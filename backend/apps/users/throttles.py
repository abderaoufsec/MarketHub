"""Throttle classes (Phase 7 of docs/todo.md).

Rates come from ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` in settings
(env-overridable).

Why not DRF's ``ScopedRateThrottle``? It reads its scope from the *view's*
``throttle_scope`` attribute, but ``api_view()`` does not copy that attribute
onto the wrapped class for function-based views — so on the login/register
views it would silently allow every request. These classes keep the scope on
the throttle itself and key by user id when authenticated, IP otherwise.
"""

from rest_framework.throttling import SimpleRateThrottle


class ClassScopedRateThrottle(SimpleRateThrottle):
    """Rate limit with the scope fixed on the throttle class."""

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginRateThrottle(ClassScopedRateThrottle):
    scope = "login"


class RegisterRateThrottle(ClassScopedRateThrottle):
    scope = "register"


class VerifyEmailRateThrottle(ClassScopedRateThrottle):
    scope = "verify_email"


class ChangePasswordRateThrottle(ClassScopedRateThrottle):
    scope = "change_password"


class TokenRefreshRateThrottle(ClassScopedRateThrottle):
    scope = "token_refresh"


class OtpRequestRateThrottle(ClassScopedRateThrottle):
    """SMS *request* rate per IP (Phase 8).

    The per-number/per-IP daily budgets in ``otp.py`` are the real
    SMS-pumping defence; this is the coarse per-IP request gate in front of
    them, so a single host cannot even reach the point of counting.
    """

    scope = "otp_request"


class OtpVerifyRateThrottle(ClassScopedRateThrottle):
    """Code *verification* rate — the endpoint a guessing attack hits."""

    scope = "otp_verify"


class ForgotPasswordRateThrottle(ClassScopedRateThrottle):
    scope = "forgot_password"


class ResendVerificationRateThrottle(ClassScopedRateThrottle):
    scope = "resend_verification"


class SocialLoginRateThrottle(ClassScopedRateThrottle):
    """Social sign-in attempts per IP (token replay / probing)."""

    scope = "social_login"


class RevealPhoneRateThrottle(ClassScopedRateThrottle):
    """Anti-scraping throttle for endpoints that expose a phone number.

    Ouedkniss-style sites are scraped aggressively; the scoped rate limits how
    fast one IP/user can harvest contact details. Attached today to the public
    store endpoints (their ``owner`` payload embeds the seller's phone number);
    the dedicated "reveal phone" endpoint in Phase 16 must reuse this class.
    """

    scope = "reveal_phone"
