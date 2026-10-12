"""URL-path API versioning (Phase 9 of docs/todo.md).

Every route lives under ``/api/v1/``. The version is part of the path rather
than a header or a query parameter because it is the only scheme a browser, a
curl one-liner and an OpenAPI generator all understand without setup, and
because a mobile client pinned to ``/api/v1/`` keeps working the day ``/v2``
ships.

``request.version`` reports ``"v1"`` for every request, including the ones
mounted without the segment (``/api/docs/``, ``/api/schema/``) — those are
version-independent by nature, so they fall back to the default instead of
tripping ``URLPathVersioning``'s assertion.
"""

from rest_framework.exceptions import NotFound
from rest_framework.versioning import URLPathVersioning


class PathVersioning(URLPathVersioning):
    default_version = "v1"
    allowed_versions = ("v1",)
    version_param = "version"

    def determine_version(self, request, *args, **kwargs):
        version = kwargs.get(self.version_param) or self.default_version
        if self.allowed_versions is not None and version not in self.allowed_versions:
            # ``URLPathVersioning`` asserts here, which would turn
            # ``/api/whatever/`` into a 500. A client that guessed the URL
            # wrong deserves the same 404 envelope as any other miss.
            raise NotFound("API version not found.")
        return version
