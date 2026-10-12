"""``Idempotency-Key`` support for endpoints that move money or create a listing.

Phase 9 of docs/todo.md. Three shapes of the same promise — *sending this
twice does not happen twice*:

* **Checkout** and **payment simulate** already replay from a body field
  (``idempotency_key``, Phase 6). Those views now also accept the standard
  header, so a mobile client does not have to invent a body field to be safe.
* **Refund** and **listing create** are *actions* rather than domain writes:
  :class:`IdempotentPostMixin` caches the first successful response per
  (user, key) and replays it, so a retried POST returns the original body
  instead of a second refund or a duplicate listing.

The key is scoped per user: two buyers using the same UUID are not each
other's replay, and an anonymous client cannot replay somebody else's
response.

Reusing a key with a *different* body is a client bug, and answering it with
the old response would hide data loss — that case is a 409
``idempotency_key_conflict``.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.core.cache import cache
from rest_framework.response import Response

from .exceptions import ApiError

logger = logging.getLogger(__name__)

#: Standard header name (RFC-ish: Stripe, Braintree and GitHub all use it).
IDEMPOTENCY_HEADER = "Idempotency-Key"

#: How long a replay is remembered. Long enough to cover a flaky mobile
#: connection retrying for minutes, short enough that the cache turns over.
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60

_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")


def validate_key(value: str) -> str:
    """Normalise and sanity-check a key. It ends up in a cache key and a log
    line, so it is restricted to a short, boring charset."""
    key = str(value or "").strip()
    if not key or len(key) > 64 or any(char not in _ALLOWED for char in key):
        raise ApiError(
            "Idempotency-Key must be 1-64 characters of [A-Za-z0-9-._].",
            code="invalid_idempotency_key",
            status_code=400,
        )
    return key


def idempotency_key(request, body_value: str | None = None) -> str | None:
    """The key for this request: the ``Idempotency-Key`` header if present,
    otherwise the body field the Phase 6 endpoints already read."""
    header = request.headers.get(IDEMPOTENCY_HEADER)
    if header:
        return validate_key(header)
    if body_value:
        return validate_key(body_value)
    return None


def _digest(request) -> str:
    """Fingerprint of the request body, so replaying a key with *different*
    data is detected instead of silently returning the first response."""
    try:
        payload = json.dumps(request.data, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - exotic bodies
        payload = repr(sorted(request.data.items(), key=lambda pair: str(pair[0])))
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()


def _cache_key(request, scope: str, key: str) -> str:
    ident = (
        request.user.pk
        if request.user and request.user.is_authenticated
        else f"anon-{request.META.get('REMOTE_ADDR', 'unknown')}"
    )
    return f"idem:{scope}:{ident}:{key}"


class IdempotentPostMixin:
    """Replay the first successful ``POST`` for a given ``Idempotency-Key``.

    Declare ``idempotency_scope`` ("refund", "listing", …) so two endpoints
    under the same user cannot collide on a key, then mix it into an
    ``APIView``/``GenericAPIView``::

        class ProductCreateView(IdempotentPostMixin, APIView):
            idempotency_scope = "listing"

    A replayed response carries ``Idempotency-Replayed: true`` so a client can
    tell the difference between "created" and "replayed" — the body and status
    are identical either way.
    """

    idempotency_scope = "generic"

    def post(self, request, *args, **kwargs):
        key = idempotency_key(request)
        if key is None:
            return super().post(request, *args, **kwargs)

        cache_key = _cache_key(request, self.idempotency_scope, key)
        cached = cache.get(cache_key)
        if cached is not None:
            if cached["digest"] != _digest(request):
                raise ApiError(
                    "This Idempotency-Key was already used with a different payload.",
                    code="idempotency_key_conflict",
                    status_code=409,
                )
            logger.info(
                "Idempotent replay %s key=%s [%s]",
                self.idempotency_scope,
                key,
                getattr(request, "request_id", "-"),
            )
            return Response(
                cached["body"],
                status=cached["status"],
                headers={"Idempotency-Replayed": "true"},
            )

        response = super().post(request, *args, **kwargs)
        if response.status_code in (200, 201):
            cache.set(
                cache_key,
                {
                    "digest": _digest(request),
                    "body": response.data,
                    "status": response.status_code,
                },
                timeout=IDEMPOTENCY_TTL_SECONDS,
            )
        return response
