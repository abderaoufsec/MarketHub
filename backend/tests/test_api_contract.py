"""The Phase 9 error contract, asserted end to end.

``docs/todo.md`` says: *400/401/403/404/429/500 share one shape, and
``/api/docs/`` lists every route*. Those two sentences are the phase, so they
are tested from the outside — through the real middleware stack, a real URL
resolution and the real exception handler, not by unit-testing the helpers in
``core/exceptions.py`` (which would only prove the helpers work).

The shape under test:

    {"code": "...", "message": "...", "details": {...}|null, "request_id": "..."}

and the two things that make it *useful* rather than merely consistent: the
``request_id`` also comes back as a header (and matches the log line), and the
``message`` follows ``Accept-Language``.
"""

import re

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework.test import APIClient

from tests.helpers import throttle_rate

pytestmark = pytest.mark.django_db

#: The envelope keys, in the order a human would read them. Asserted as a
#: *set* so adding a field later is a deliberate decision rather than an
#: accidental one.
ENVELOPE_KEYS = {"code", "message", "details", "request_id"}

REGISTER_URL = "/api/v1/auth/register/"
CART_URL = "/api/v1/orders/cart/"


def assert_envelope(response, *, status, code=None):
    """Assert the response is a well-formed Phase 9 failure."""
    assert response.status_code == status
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    if code is not None:
        assert body["code"] == code
    assert isinstance(body["code"], str) and body["code"]
    assert re.fullmatch(r"[a-z0-9_]+", body["code"])
    assert isinstance(body["message"], str) and body["message"]
    assert body["request_id"] == response["X-Request-ID"]
    return body


# ---------------------------------------------------------------------------
# One shape per status
# ---------------------------------------------------------------------------
def test_400_carries_field_errors_in_details(api_client):
    """A serializer rejection is the commonest failure there is: the field
    dict moves into ``details``, and the envelope gains no invented keys."""
    response = api_client.post(REGISTER_URL, {})

    body = assert_envelope(response, status=400, code="validation_error")
    assert isinstance(body["details"], dict)
    assert any(body["details"].values()), "details should carry the field errors"
    for messages in body["details"].values():
        assert isinstance(messages, list)
        assert all(isinstance(message, str) for message in messages)


def test_401_unauthenticated_envelope(api_client):
    """An anonymous caller at a logged-in endpoint."""
    response = api_client.get(CART_URL)

    assert_envelope(response, status=401, code="not_authenticated")


def test_403_permission_denied_envelope(buyer_client, product):
    """A logged-in caller who is not allowed to do *this*."""
    response = buyer_client.put(f"/api/v1/products/seller/{product.id}/", {})

    body = assert_envelope(response, status=403)
    assert body["code"] != "validation_error"


def test_404_not_found_envelope(api_client):
    """A missing object, addressed through a DRF view."""
    response = api_client.get("/api/v1/products/99999999/")

    assert_envelope(response, status=404)


def test_404_unknown_api_path_is_json_not_html(api_client):
    """Django resolves the URL *before* DRF is involved, so its 404 page is
    HTML. ``ApiContractMiddleware`` rewrites it — a client under ``/api/``
    must never have to parse an HTML error page."""
    response = api_client.get("/api/v1/there-is-no-such-route/")

    assert_envelope(response, status=404, code="not_found")


def test_405_wrong_method_is_json_not_html(api_client):
    """``http_method_not_allowed`` is reached before any body is parsed, so
    the envelope has nothing to say but the status."""
    response = api_client.get("/api/v1/auth/login/")

    assert_envelope(response, status=405, code="method_not_allowed")


def test_429_throttled_envelope(api_client):
    """The rate limiter speaks the same shape, and still hands the client the
    one number it needs (``Retry-After`` keeps working)."""
    with throttle_rate("login", "1/min"):
        api_client.post("/api/v1/auth/login/", {})
        response = api_client.post("/api/v1/auth/login/", {})

    body = assert_envelope(response, status=429, code="throttled")
    assert response["Retry-After"]
    assert body["details"]["wait"] >= 0


# ---------------------------------------------------------------------------
# 500: the status DRF's handler never sees
# ---------------------------------------------------------------------------
def _explode(request):
    raise RuntimeError("deliberate test explosion")


urlpatterns = [path("api/v1/__explode__/", _explode)]


@override_settings(ROOT_URLCONF="tests.test_api_contract")
def test_500_unhandled_exception_is_logged_and_hidden(api_client):
    """A bug must not leak a traceback to the client, and must not escape the
    envelope either. The request id is what ties the (anonymous) 500 back to
    the traceback in the log.

    Uses Django's client rather than DRF's: ``APIClient.get`` forwards
    ``**extra`` as WSGI environ, so ``raise_request_exception=False`` would be
    ignored and the test would die on the very exception it is asserting
    about.
    """
    client = Client(raise_request_exception=False)
    response = client.get("/api/v1/__explode__/")

    body = assert_envelope(response, status=500, code="server_error")
    assert "deliberate test explosion" not in response.content.decode()
    assert body["request_id"]


# ---------------------------------------------------------------------------
# Correlation id
# ---------------------------------------------------------------------------
def test_request_id_is_client_supplied_when_well_formed(api_client):
    """A client that traces its own requests gets its id back everywhere."""
    response = api_client.get(CART_URL, HTTP_X_REQUEST_ID="mobile-42-eu-west-1")

    assert response["X-Request-ID"] == "mobile-42-eu-west-1"
    assert response.json()["request_id"] == "mobile-42-eu-west-1"


def test_hostile_request_id_is_replaced(api_client):
    """The header is echoed into a response header and a log line, so it is
    not trusted as-is (CRUD, log-forging)."""
    response = api_client.get(CART_URL, HTTP_X_REQUEST_ID="a b\nc")

    request_id = response["X-Request-ID"]
    assert " " not in request_id and "\n" not in request_id
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert response.json()["request_id"] == request_id


def test_success_responses_carry_the_id_too(api_client):
    """Correlation is only useful if it is on every response."""
    response = api_client.get("/api/v1/products/")

    assert response["X-Request-ID"]
    assert "code" not in response.json()


# ---------------------------------------------------------------------------
# Localisation (Accept-Language)
# ---------------------------------------------------------------------------
def test_message_follows_accept_language(api_client):
    """``message`` is translated, so a French or Arabic user does not get an
    English error. ``code`` deliberately does *not* move: it is the stable
    thing clients branch on."""
    messages = {}
    for language in ("en", "fr", "ar"):
        response = api_client.post(REGISTER_URL, {}, HTTP_ACCEPT_LANGUAGE=language)
        body = assert_envelope(response, status=400, code="validation_error")
        messages[language] = body["message"]

    assert len(set(messages.values())) == 3, f"expected three distinct translations, got {messages}"
    assert messages["en"] != messages["fr"] != messages["ar"]


def test_drffield_errors_are_translated_too(api_client):
    """DRF's own catalogue ships fr/ar, and the field messages ride through
    ``details`` — so they follow the language as well."""
    english = api_client.post(REGISTER_URL, {}, HTTP_ACCEPT_LANGUAGE="en").json()
    french = api_client.post(REGISTER_URL, {}, HTTP_ACCEPT_LANGUAGE="fr").json()

    english_field = next(iter(english["details"].values()))[0]
    french_field = next(iter(french["details"].values()))[0]
    assert english_field != french_field


def test_an_unsupported_language_falls_back(api_client):
    """``Accept-Language`` is a preference, not a command."""
    response = api_client.post(REGISTER_URL, {}, HTTP_ACCEPT_LANGUAGE="zz-qaa-derp")

    assert_envelope(response, status=400, code="validation_error")


# ---------------------------------------------------------------------------
# OpenAPI (Phase 9 "machine-readable docs" half)
# ---------------------------------------------------------------------------
def _django_api_paths():
    from django.urls import get_resolver

    def walk(resolver, prefix=""):
        found = []
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                found.extend(walk(pattern, prefix + str(pattern.pattern)))
            else:
                found.append(prefix + str(pattern.pattern))
        return found

    return {
        "/" + path
        for path in walk(get_resolver())
        # Restricted to the versioned API: drf-spectacular deliberately omits
        # the docs endpoints themselves (SERVE_INCLUDE_SCHEMA=False keeps
        # /api/schema/ out of its own output), and the phase is about the API.
        if path.startswith("api/v1/")
    }


def _normalise(pattern):
    """``/api/v1/products/<int:pk>/`` -> ``/api/v1/products/{id}/``.

    drf-spectacular renames ``pk`` to ``id`` in its operation paths, so the
    rename is mirrored here rather than reported as a missing route.
    """
    pattern = re.sub(r"<[^:>]+:([^>]+)>", r"{\1}", pattern)
    pattern = re.sub(r"<[^>]+>", "{}", pattern)
    return pattern.replace("{pk}", "{id}")


@pytest.fixture(scope="module")
def schema():
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def test_every_route_is_documented(schema):
    """ "/api/docs/ lists every route" — the phase's own acceptance test."""
    documented = set(schema["paths"])
    registered = {_normalise(path) for path in _django_api_paths()}

    missing = sorted(registered - documented)
    ghost = sorted(documented - registered)
    assert not missing, f"routes missing from the schema: {missing}"
    assert not ghost, f"schema documents routes that do not exist: {ghost}"


def test_every_operation_is_tagged(schema):
    """Grouping comes from the URL (``core/schema.py``), so a route cannot be
    added to the docs untagged."""
    untagged = [
        (method, path)
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict) and "operationId" in operation and not operation.get("tags")
    ]
    assert not untagged, f"operations without a tag: {untagged}"


def test_mutating_operations_document_their_request_body(schema):
    """A docs page that will not tell you what to POST is decoration. Views
    that take no body (``POST /logout/``) are allowed to omit it."""
    bodyless = [
        (method, path)
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict)
        and "operationId" in operation
        and method in ("post", "put", "patch")
        and not operation.get("requestBody")
    ]
    assert not bodyless, f"mutating operations with no request body: {bodyless}"


@pytest.mark.parametrize("url", ["/api/docs/", "/api/redoc/", "/api/schema/"])
def test_docs_endpoints_are_served(api_client, url):
    response = api_client.get(url)

    assert response.status_code == 200


def test_schema_is_machine_readable(api_client):
    """YAML is the default rendering; ask for JSON and you get it — the point
    being that a machine, not a browser, is the primary consumer."""
    response = api_client.get("/api/schema/", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    assert "openapi" in response.json()


# ---------------------------------------------------------------------------
# Versioning (Phase 9 "before a mobile app depends on it")
# ---------------------------------------------------------------------------
def test_the_api_is_served_under_a_versioned_path(api_client):
    """The version is in the URL, so it survives proxies and is visible in a
    stack trace. ``request.version`` reports it, and the response says so."""
    response = api_client.get("/api/v1/products/")

    assert response.status_code == 200
    assert response["X-API-Version"] == "v1"


def test_the_versioning_scheme_reports_the_mounted_version():
    """``request.version`` is a lazy property nothing currently reads, so the
    scheme is pinned directly rather than left uncovered."""
    from rest_framework.test import APIRequestFactory

    from core.versioning import PathVersioning

    request = APIRequestFactory().get("/api/v1/products/")
    assert PathVersioning().determine_version(request, **{}) == "v1"


def test_a_version_outside_the_allowed_set_is_refused():
    """``URLPathVersioning`` *asserts* here, which would turn a guessed URL
    into a 500; refusing it keeps it a 404 like any other miss."""
    from rest_framework.exceptions import NotFound
    from rest_framework.test import APIRequestFactory

    from core.versioning import PathVersioning

    request = APIRequestFactory().get("/api/v2/products/")
    with pytest.raises(NotFound):
        PathVersioning().determine_version(request, version="v2")


def test_an_unversioned_api_path_is_not_served(api_client):
    """There is exactly one contract, under one prefix: an old unversioned
    client gets the same 404 shape as everything else."""
    response = api_client.get("/api/products/")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# ---------------------------------------------------------------------------
# Non-API paths are left alone
# ---------------------------------------------------------------------------
def test_django_html_pages_are_not_rewritten(api_client):
    """The middleware only speaks for ``/api/``; everything else keeps
    Django's own (HTML) 404. A non-API path, because ``/admin/`` answers an
    unknown page with a redirect to its login instead."""
    response = api_client.get("/definitely-not-a-page/")

    assert response.status_code == 404
    assert "text/html" in response["Content-Type"]
    assert "code" not in response.content.decode()


def test_the_admin_site_is_left_alone(api_client):
    """The admin is a Django app, not part of the API contract."""
    response = api_client.get("/admin/definitely-not-a-page/")

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
