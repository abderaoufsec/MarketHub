"""Social login providers — Phase 8 of docs/todo.md ("optional social login,
since Facebook is dominant in Algeria").

Zero new dependencies: both providers are plain HTTPS calls verified
**server-side** against Google/Facebook — the token the browser hands us is
never trusted, only replayed to the issuer that minted it.

* **Google** — the ID token from Google Sign-In is checked against
  ``tokeninfo``, which validates the signature and returns the claims; we then
  check the audience (``GOOGLE_CLIENT_ID``), the issuer and
  ``email_verified``. An unverified provider email is refused: it would be an
  account-takeover path (attacker registers the victim's address at a sloppy
  provider and inherits any future link).
* **Facebook** — with ``FACEBOOK_APP_ID``/``FACEBOOK_APP_SECRET`` configured
  the access token is first checked through ``debug_token`` (audience + validity
  + expiry, the app-secret-proof variant), then ``/me`` returns the profile.

Every transport failure or bad answer becomes :class:`SocialError` with an
HTTP-safe message — no raw provider payloads ever reach a response body.
Configuration gaps answer 503 (provider not deployed), not 400.
"""

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("apps.users.social")

GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GRAPH_URL = "https://graph.facebook.com"


class SocialError(Exception):
    """Provider refused, misconfigured, or unreachable."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class SocialProfile:
    """Normalized identity a provider vouched for."""

    __slots__ = ("email", "first_name", "last_name", "provider", "provider_user_id")

    def __init__(self, provider, provider_user_id, email, first_name="", last_name=""):
        self.provider = provider
        self.provider_user_id = str(provider_user_id)
        self.email = email
        self.first_name = first_name or ""
        self.last_name = last_name or ""


def _get_json(url: str) -> dict:
    """GET a provider endpoint and decode the JSON answer (timeout-bounded)."""
    request = urllib.request.Request(url, headers={"User-Agent": "MarketHub/identity"})
    try:
        with urllib.request.urlopen(request, timeout=settings.SOCIAL_HTTP_TIMEOUT) as response:
            if response.status >= 400:
                raise SocialError("Social provider refused the request.", status=502)
            payload = json.loads(response.read().decode("utf-8"))
    except SocialError:
        raise
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("social provider unreachable: %s", exc)
        raise SocialError("Could not reach the social provider.", status=502) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("social provider sent a non-JSON answer: %s", exc)
        raise SocialError("The social provider sent an invalid response.", status=502) from exc

    if not isinstance(payload, dict):
        raise SocialError("The social provider sent an invalid response.", status=502)
    # Providers signal a bad token as {"error": {...}} rather than an HTTP 4xx.
    if "error" in payload:
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        logger.info("social token rejected: %s", message)
        raise SocialError("That sign-in token is invalid or expired.")
    return payload


def fetch_google(id_token: str) -> SocialProfile:
    """Verify a Google ID token and return the profile it vouches for."""
    if not settings.GOOGLE_CLIENT_ID:
        raise SocialError("Google sign-in is not configured.", status=503)

    claims = _get_json(f"{GOOGLE_TOKENINFO}?{urllib.parse.urlencode({'id_token': id_token})}")

    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise SocialError("That sign-in token was issued for another application.")
    issuer = str(claims.get("iss") or "")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        raise SocialError("That sign-in token was not issued by Google.")
    if str(claims.get("email_verified", "")).lower() != "true":
        raise SocialError("Your Google account email address is not verified.")
    if not claims.get("email"):
        raise SocialError("Your Google account has no email address.")

    return SocialProfile(
        provider="google",
        provider_user_id=claims.get("sub") or claims.get("email"),
        email=claims["email"],
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
    )


def fetch_facebook(access_token: str, app_id: str, app_secret: str) -> SocialProfile:
    """Verify a Facebook access token (debug_token) and fetch the profile."""
    proof = hmac.new(app_secret.encode("utf-8"), access_token.encode("utf-8"), hashlib.sha256)

    # 1. Is the token valid *for our app*? (audience check — a token minted
    #    for a different app must not log anyone in here.)
    debug = _get_json(
        f"{GRAPH_URL}/debug_token?"
        + urllib.parse.urlencode(
            {
                "input_token": access_token,
                "access_token": f"{app_id}|{app_secret}",
            }
        )
    ).get("data")
    if not isinstance(debug, dict):
        raise SocialError("The social provider sent an invalid response.", status=502)
    if not debug.get("is_valid") or debug.get("app_id") != app_id:
        raise SocialError("That sign-in token is invalid or expired.")

    # 2. Profile — appsecret_proof makes a stolen token useless off-app.
    me = _get_json(
        f"{GRAPH_URL}/me?"
        + urllib.parse.urlencode(
            {
                "fields": "id,email,first_name,last_name",
                "access_token": access_token,
                "appsecret_proof": proof.hexdigest(),
            }
        )
    )
    if not me.get("email"):
        raise SocialError(
            "This Facebook account has no email address. Sign up with your phone number instead."
        )
    return SocialProfile(
        provider="facebook",
        provider_user_id=me.get("id"),
        email=me["email"],
        first_name=me.get("first_name", ""),
        last_name=me.get("last_name", ""),
    )


def get_social_profile(provider: str, token: str) -> SocialProfile:
    """Dispatch to the configured provider. ``SocialError`` on any failure."""
    if not token:
        raise SocialError("Missing social sign-in token.")

    if provider == "google":
        return fetch_google(token)
    if provider == "facebook":
        if not (settings.FACEBOOK_APP_ID and settings.FACEBOOK_APP_SECRET):
            raise SocialError("Facebook sign-in is not configured.", status=503)
        return fetch_facebook(token, settings.FACEBOOK_APP_ID, settings.FACEBOOK_APP_SECRET)
    raise SocialError("Unsupported social provider.")
