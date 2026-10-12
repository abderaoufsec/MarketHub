"""OpenAPI generation helpers (Phase 9 of docs/todo.md).

``drf-spectacular`` already walks every registered view and emits an
operation per route. What it cannot know is *how this project groups its
API*, so the tag for an operation is derived from its path:

    /api/v1/auth/login/    -> auth
    /api/v1/orders/cart/   -> orders
    /api/docs/             -> docs

Doing that in one postprocessing hook instead of repeating
``@extend_schema(tags=[...])`` on ~40 function-based views means a route
cannot be added without a tag — the docs stay grouped as the API grows, and
``test_api_contract.py`` can assert that every operation carries one.
"""

from __future__ import annotations

#: Longest prefix first: ``/api/v1/`` must win over ``/api/``.
PATH_PREFIXES = ("/api/v1/", "/api/")


def tag_for_path(path: str) -> str:
    for prefix in PATH_PREFIXES:
        if path.startswith(prefix):
            remainder = path[len(prefix) :]
            break
    else:
        remainder = path.lstrip("/")
    segment = remainder.split("/", 1)[0]
    return segment or "api"


def tag_operations(result, generator, request, public):
    """Give every operation a tag (first path segment) without clobbering one
    a view already declared with ``@extend_schema``."""
    for path, operations in (result.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        tag = tag_for_path(path)
        for operation in operations.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue  # path-level ``parameters`` and friends
            tags = operation.setdefault("tags", [])
            if tag not in tags:
                tags.insert(0, tag)
    return result
