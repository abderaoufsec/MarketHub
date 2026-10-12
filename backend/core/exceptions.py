"""The one error contract for every ``/api/`` response (Phase 9 of docs/todo.md).

Before this, every app invented its own failure body: ``{"error": …}``,
``{"detail": …}``, ``{"error": …, "code": …}``, sometimes a bare serializer
field dict. A client (or a log-scavenging developer) had to know which app it
was talking to in order to read the failure. Now every failure — DRF
validation, a raised domain error, a throttled request, an unhandled
exception — is rendered as one envelope::

    {
      "code": "insufficient_stock",
      "message": "Not enough stock left for “E2E Test Phone”.",
      "details": {"lines": [...]},          # or the field errors, or null
      "request_id": "8f14e45fceea167a5a36dedd4bea2543"
    }

* ``code`` — stable and machine-readable; clients branch on it. Every code in
  use is catalogued in ``docs/error-codes.md``.
* ``message`` — human text, translated into the language the client asked for
  with ``Accept-Language`` (the catalogue lives in ``backend/locale``).
* ``details`` — structured extras: ``{field: [messages]}`` for validation,
  the offending lines for ``price_changed``, ``{"wait": 30}`` for a throttle.
  ``null`` when there is nothing more to say.
* ``request_id`` — the same value as the ``X-Request-ID`` response header and
  the one printed in the server log, so a user can quote it in a bug report
  and the line can be found again.

Success bodies are untouched: this module only shapes *failures*.
"""

from __future__ import annotations

import logging
import uuid

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework.exceptions import (
    APIException,
    ErrorDetail,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

#: Header carrying the correlation id in both directions.
REQUEST_ID_HEADER = "X-Request-ID"

#: Used when a failure carries a dict of field errors: the field messages are
#: in ``details``, so the top-level ``message`` is the one line that sums up
#: the problem for a toast or a log.
VALIDATION_MESSAGE = "Some of the submitted values are invalid."

#: Last-resort code when neither the exception nor its DRF default says
#: anything useful (a status we have never seen).
FALLBACK_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    402: "payment_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "throttled",
    500: "server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class ApiError(APIException):
    """An expected failure with a code clients can branch on.

    Use this instead of building a ``{"error": …}`` dict by hand::

        raise ApiError("Invalid or expired reset link.", code="invalid_reset_token")

    ``details`` carries structured extras (a price delta, a stock count) and
    lands in the envelope verbatim.
    """

    status_code = 400
    default_code = "bad_request"

    def __init__(self, detail=None, *, code=None, details=None, status_code=None):
        # ``code`` resolution matters here: domain exceptions (see
        # apps/orders/exceptions.py) declare a *class-level* ``code`` such as
        # ``empty_cart``, and super().__init__ would otherwise replace it with
        # default_code when no code is passed. Set it first — resolve_code()
        # reads it before anything else. The message is translated later, when
        # the envelope is built (the request's language is active by then).
        self.code = code or getattr(type(self), "code", None) or self.default_code
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=detail, code=self.code)


class InternalServerError(ApiError):
    """A handled server-side failure: the client gets a usable message, the
    log keeps the traceback (see where it is raised)."""

    status_code = 500
    default_code = "server_error"

    def __init__(self, detail=None, *, code=None, details=None, cause=None):
        if cause is not None:
            logger.exception("API 500 [%s]: %s", self.default_code, detail, exc_info=cause)
        super().__init__(detail=detail, code=code, details=details)


def build_error_body(*, code, message, details=None, request_id=None):
    """The envelope itself — one place, so no route can drift from it."""
    return {
        "code": str(code),
        "message": _(str(message)),
        "details": details,
        "request_id": str(request_id or uuid.uuid4().hex),
    }


def _iter_error_details(detail):
    """Depth-first walk of a DRF ``detail`` tree, yielding ``ErrorDetail``."""
    if isinstance(detail, ErrorDetail):
        yield detail
    elif isinstance(detail, dict):
        for value in detail.values():
            yield from _iter_error_details(value)
    elif isinstance(detail, (list, tuple)):
        for item in detail:
            yield from _iter_error_details(item)


def resolve_code(exc, detail):
    """Pick the machine-readable code, most specific first.

    1. ``exc.code`` — set by :class:`ApiError` and the domain exceptions
       (``price_changed``, ``empty_cart``, …). This is the branchable one.
    2. A ``ValidationError`` without such a code: the payload is a field dict,
       so a single top-level ``validation_error`` describes it.
    3. The ``ErrorDetail`` code DRF attached (``not_found`` on a
       ``NotFound``, ``permission_denied`` on a permission failure, or an
       explicit ``code=`` the view passed in).
    4. The exception's ``default_code``, then the status-code table.
    """
    explicit = getattr(exc, "code", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    if isinstance(exc, ValidationError):
        return "validation_error"
    for err in _iter_error_details(detail):
        if err.code:
            return str(err.code)
    default = getattr(exc, "default_code", None)
    if isinstance(default, str) and default:
        return default
    return FALLBACK_CODES.get(getattr(exc, "status_code", 500), "server_error")


def resolve_message(exc, detail):
    """The single human sentence.

    A string detail is the message itself. A field dict has no single
    sentence — the caller reads ``details[field][0]`` — so it is summarised.
    """
    if isinstance(detail, dict):
        return VALIDATION_MESSAGE
    if isinstance(detail, (list, tuple)):
        # e.g. DjangoValidationError flattened by DRF: "Enter a valid email…"
        first = next(iter(_iter_error_details(detail)), None)
        return str(first) if first is not None else VALIDATION_MESSAGE
    if detail is not None:
        return str(detail)
    return "The request could not be processed."


def resolve_details(exc, detail):
    """Structured extras, normalised so ``details`` has one of three shapes:
    a dict of field messages, a JSON-serialisable payload, or ``None``."""
    extra = getattr(exc, "details", None)
    if extra is not None:
        return extra
    if isinstance(exc, ValidationError):
        if isinstance(detail, dict):
            return {
                str(key): [str(message) for message in _as_messages(value)]
                for key, value in detail.items()
            }
        if isinstance(detail, (list, tuple)):
            return {"non_field_errors": [str(message) for message in _as_messages(detail)]}
        return None
    wait = getattr(exc, "wait", None)
    if wait is not None:
        # DRF also sends Retry-After; this is for clients that only read JSON.
        return {"wait": wait}
    if isinstance(detail, (dict, list, tuple)):
        if isinstance(detail, dict):
            return {
                str(key): [str(message) for message in _as_messages(value)]
                for key, value in detail.items()
            }
        return [str(message) for message in _as_messages(detail)]
    return None


def _as_messages(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def to_api_exception(exc):
    """Map the Django exceptions DRF translates onto their DRF twins.

    DRF's own handler does this rebinding *inside* its function, so the
    object this module sees is still an ``Http404`` or a
    ``django.core.exceptions.PermissionDenied``, neither of which has a
    ``detail``. Normalising first means ``resolve_code``/``resolve_message``
    see one shape — and that a plain-Django view raising ``Http404`` under
    ``/api/`` answers like a DRF one instead of as a 500.

    This mirrors ``rest_framework.views.exception_handler`` exactly; DRF does
    not translate ``DjangoValidationError`` here (serializers raise their own
    ``ValidationError`` before it can reach the handler).
    """
    if isinstance(exc, APIException):
        return exc
    if isinstance(exc, Http404):
        return NotFound(*(exc.args or ()))
    if isinstance(exc, DjangoPermissionDenied):
        return PermissionDenied(*(exc.args or ()))
    return exc


def api_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER``: render any APIException as the envelope.

    Returning ``None`` hands the exception back to DRF, which re-raises it and
    lets Django produce a 500 — ``ApiContractMiddleware`` wraps that one in the
    same envelope, so no status escapes the contract.
    """
    exc = to_api_exception(exc)
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None) or _request_id_from(request)
    detail = exc.detail

    response.data = build_error_body(
        code=resolve_code(exc, detail),
        message=resolve_message(exc, detail),
        details=resolve_details(exc, detail),
        request_id=request_id,
    )
    return response


def _request_id_from(request):
    """Fall back to the client's ``X-Request-ID`` (or a fresh id) when the
    middleware did not run — e.g. a unit test calling the handler directly."""
    if request is None:
        return uuid.uuid4().hex
    return valid_request_id(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex


def valid_request_id(value):
    """Accept a client-supplied id only if it is short and boring: it is about
    to be echoed into a response header and a log line."""
    if not value or len(value) > 64:
        return None
    if any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._"
        for char in value
    ):
        return None
    return value
