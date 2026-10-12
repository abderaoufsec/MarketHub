"""OpenAPI security scheme for ``CookieJWTAuthentication`` (Phase 9).

drf-spectacular resolves every authenticator through an
``OpenApiAuthenticationExtension``; without one it logs
``could not resolve authenticator … CookieJWTAuthentication`` for **every**
operation in the project — that class is
``REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`` (core/settings.py), so
this single extension fixes the warning on all apps at once.

``authentication.py`` accepts either credential: the ``Authorization: Bearer``
header first, then the ``access_token`` HttpOnly cookie. Because one is
enough, the operations document the two schemes as an **OR**: a *list* of
security requirement dicts. One dict with both keys would be an AND — a
request expected to carry header *and* cookie — which is not what the code
does (see ``OpenApiAuthenticationExtension.get_security_requirement``).
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .cookies import ACCESS_COOKIE


class CookieJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Describe the two ways a client can present its access token."""

    target_class = "apps.users.authentication.CookieJWTAuthentication"
    name = ["BearerAuth", "CookieAuth"]

    def get_security_definition(self, auto_schema):
        # One definition per entry in ``name``, in the same order — the
        # generator zips them together into two components.
        return [
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Access token issued by the refresh endpoint. Preferred by API "
                    "and mobile clients: it is sent explicitly, so no CSRF token is "
                    "required."
                ),
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": ACCESS_COOKIE,
                "description": (
                    "HttpOnly access-token cookie set on login/refresh — what the web "
                    "frontend uses. The browser attaches it automatically, so unsafe "
                    "requests must also carry the double-submit `X-CSRFToken` header."
                ),
            },
        ]

    def get_security_requirement(self, auto_schema):
        # OR, not AND: ``CookieJWTAuthentication.authenticate`` tries the
        # header and falls back to the cookie, so either alone authenticates.
        return [{"BearerAuth": []}, {"CookieAuth": []}]
