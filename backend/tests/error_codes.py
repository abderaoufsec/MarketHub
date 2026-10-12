"""Discover every error code the backend can emit, by reading the source.

This is deliberately static (AST, not runtime): a code hidden behind a helper
or a status→code dict still has to be documented, and the only way to notice
one that never fires in the test suite is to go and look at the code.

Three shapes are recognised, in increasing order of looseness:

1. ``ApiError("…", code="some_code")`` — a kwarg on any call.
2. ``code = "some_code"`` as a class attribute (the domain exception family,
   and the permission classes DRF 3.16 reads `code` from).
3. Indirect plumbing: a helper's trailing string argument
   (``_phone_conflict(message, "phone_already_registered")``), the default of
   a status→code lookup (``_SOCIAL_ERROR_CODES.get(status, "…")``), and dicts
   whose *every* value is snake_case (``_SOCIAL_ERROR_CODES = {400: "…"}``).

Rule 3 is the loose one, so it only fires on a dict when all of its values
look like codes — a table of headers, paths or MIME types does not qualify.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: Lower snake_case with at least one underscore. Codes are never single
#: words (``detail``-style DRF codes are handled separately), never CamelCase
#: and never contain a space, which is what keeps messages out.
CODE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

#: Attributes that carry a code, on both exceptions and permission classes.
CODE_ATTRIBUTES = frozenset({"code", "default_code"})

#: Where not to look: migrations say nothing about the contract, and tests
#: are allowed to assert on codes that no view can produce any more.
SKIP_PARTS = frozenset({"migrations", "tests", "__pycache__"})


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in (BACKEND / "core", *sorted((BACKEND / "apps").glob("*"))):
        if not root.is_dir():
            continue
        files.extend(
            path for path in sorted(root.rglob("*.py")) if not SKIP_PARTS.intersection(path.parts)
        )
    return files


def collect_codes() -> dict[str, list[str]]:
    """``{"some_code": ["apps/users/views.py:485", …]}`` for every code found."""
    found: dict[str, set[str]] = defaultdict(set)

    for path in _source_files():
        relative = path.relative_to(BACKEND).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            # 1. `code="…"` on a call.
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if (
                        keyword.arg == "code"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                        and CODE.match(keyword.value.value)
                    ):
                        found[keyword.value.value].add(f"{relative}:{node.lineno}")

                # 3a. `_helper(message, "some_code")`.
                name = _called_name(node)
                if name.startswith("_") and node.args:
                    tail = node.args[-1]
                    if (
                        isinstance(tail, ast.Constant)
                        and isinstance(tail.value, str)
                        and CODE.match(tail.value)
                    ):
                        found[tail.value].add(f"{relative}:{node.lineno} {name}()")

                # 3b. `_SOME_CODES.get(status, "default_code")` — the fallback
                #     of a status→code lookup is a code too, and it is the one
                #     most likely to go unmentioned when the map is edited.
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and len(node.args) == 2
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id.endswith("_CODES")
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                    and CODE.match(node.args[1].value)
                ):
                    found[node.args[1].value].add(f"{relative}:{node.lineno} .get()")

            # 2. `code = "…"` as a class/instance attribute.
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id in CODE_ATTRIBUTES
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                        and CODE.match(node.value.value)
                    ):
                        found[node.value.value].add(f"{relative}:{node.lineno}")

            # 3c. `{400: "code_a", 502: "code_b"}` — only when *every* value
            #     looks like a code, so a dict of headers cannot slip in.
            elif isinstance(node, ast.Dict) and node.values:
                values = [
                    value
                    for value in node.values
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                ]
                if len(values) >= 2 and all(CODE.match(v.value) for v in values):
                    for value in values:
                        found[value.value].add(f"{relative}:{node.lineno} dict")

    return {code: sorted(where) for code, where in sorted(found.items())}
