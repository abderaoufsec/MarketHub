"""Request correlation and the error contract for failures DRF never sees.

Two jobs, one place in the stack:

1. **``X-Request-ID``** — every ``/api/`` request gets an id (the client's, if
   it sent a well-formed one, else a fresh one). It is echoed in the response
   header *and* printed in the log line for that request, which is what makes
   "it said request_id 8f14e45f…" a useful bug report.
2. **No escape from the envelope** — DRF's ``EXCEPTION_HANDLER`` covers what
   its views raise, but Django still owns URL-resolution 404s, 405s and any
   exception that escapes a view. Those come back as HTML error pages. Both
   hooks below rebuild them as the ``{code, message, details, request_id}``
   body, so *no* status under ``/api/`` can answer in another shape.

``_finish`` only rewrites responses that are not already JSON, so a DRF reply
(including its own error envelope) passes through untouched.
"""

from __future__ import annotations

import json
import logging
import uuid

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import SuspiciousOperation
from django.core.signals import got_request_exception
from django.http import Http404, HttpResponse

from .exceptions import (
    FALLBACK_CODES,
    REQUEST_ID_HEADER,
    build_error_body,
    valid_request_id,
)

logger = logging.getLogger(__name__)

API_PREFIX = "/api/"

#: Message used when the status itself says everything (an unknown URL, a
#: method the route does not implement).
STATUS_MESSAGES = {
    404: "Not found.",
    405: "Method not allowed.",
    406: "Not acceptable.",
    409: "Conflict.",
    415: "Unsupported media type.",
    429: "Too many requests. Try again later.",
    500: "An unexpected error occurred. Please try again.",
    502: "An upstream service is unavailable. Try again shortly.",
    503: "The service is temporarily unavailable. Try again shortly.",
}
DEFAULT_MESSAGE = "The request could not be processed."


def is_api_request(request) -> bool:
    return request.path.startswith(API_PREFIX)


class ApiContractMiddleware:
    """Synchronous middleware: assigns the id on the way in, enforces the
    envelope on the way out."""

    def __init__(self, get_response):
        self.get_response = get_response
        # Fail fast at boot rather than on the first error response.
        if not callable(self.get_response):
            raise TypeError("get_response must be a callable")

    def __call__(self, request):
        request.request_id = (
            valid_request_id(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex
        )
        response = self.get_response(request)
        return self._finish(request, response)

    # -- what escapes a DRF view ------------------------------------------------
    def process_exception(self, request, exception):
        """Called for exceptions raised by the *view callback* that DRF did not
        turn into a response — i.e. everything that would have been a 500."""
        if not is_api_request(request):
            return None
        if isinstance(
            exception,
            (Http404, DjangoPermissionDenied, SuspiciousOperation),
        ):
            # Django has a meaningful status for these; _finish() turns the
            # HTML it produces into the envelope, so let it.
            return None

        logger.error(
            "Unhandled exception on %s %s [request_id=%s]",
            request.method,
            request.path,
            getattr(request, "request_id", "-"),
            exc_info=True,
        )
        # Keep Django's error reporters working (they listen to this signal).
        got_request_exception.send(sender=self.__class__, request=request)
        return _json_response(
            500,
            code="server_error",
            message=STATUS_MESSAGES[500],
            request_id=getattr(request, "request_id", None),
        )

    # -- what reaches the client ----------------------------------------------
    def _finish(self, request, response):
        if not is_api_request(request):
            return response

        request_id = getattr(request, "request_id", None)
        if request_id:
            response[REQUEST_ID_HEADER] = request_id

        # Which contract this response answers to. Handy in a proxy log, and
        # it makes "which version served this?" a header read away. The
        # versioning class reports the default when the URL carries no
        # version kwarg (core/urls.py mounts a literal segment), so the path
        # is the one place that always knows.
        version = _version_from(request)
        if version:
            response["X-API-Version"] = version

        if response.status_code >= 400 and not _is_json(response):
            return _rewrite(request, response, request_id)
        return response


def _is_json(response: HttpResponse) -> bool:
    return "application/json" in response.get("Content-Type", "")


def _version_from(request):
    """The ``v1`` in ``/api/v1/...``, or ``None`` for the unversioned
    docs routes.

    Read off the path rather than the URL kwargs: the version is a literal
    segment (see core/urls.py) precisely so that ~40 function-based views do
    not have to accept an argument they never use.
    """
    match = getattr(request, "resolver_match", None)
    from_kwargs = match.kwargs.get("version") if match else None
    if from_kwargs:
        return from_kwargs
    remainder = request.path[len(API_PREFIX) :]
    return remainder.split("/", 1)[0] or None


def _rewrite(request, response, request_id):
    """Rebuild a non-JSON error page (Django's 404/405/500 HTML) as the
    envelope, keeping the status and every header worth keeping."""
    status = response.status_code
    code = FALLBACK_CODES.get(status, f"http_{status}")
    message = STATUS_MESSAGES.get(status, DEFAULT_MESSAGE)

    if status == 500:
        logger.error(
            "Server error on %s %s [%s request_id=%s]",
            request.method,
            request.path,
            code,
            request_id or "-",
        )

    return _json_response(
        status,
        code=code,
        message=message,
        request_id=request_id,
        headers=dict(response.items()),
    )


def _json_response(status, *, code, message, details=None, request_id=None, headers=None):
    body = build_error_body(code=code, message=message, details=details, request_id=request_id)
    rendered = HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status=status,
        content_type="application/json; charset=utf-8",
    )
    for header, value in (headers or {}).items():
        # The body is ours now; never carry over the HTML content headers.
        if header.lower() in {"content-type", "content-length", "content-language"}:
            continue
        rendered[header] = value
    return rendered
