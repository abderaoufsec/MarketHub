"""`docs/error-codes.md` must describe exactly what the API can emit.

The reference doc is only worth having while it is true, and a doc nobody can
forget to update is a doc that stays true. So both directions are asserted:

* every code found in the source appears here (a new failure mode cannot ship
  undocumented), and
* every code documented here still exists — in the source, or in the handful
  the contract itself produces (`core.exceptions.FALLBACK_CODES` and the
  codes `resolve_code` names explicitly), so a removed error does not linger
  as a lie.

The status column is checked too: a code with no HTTP status is useless to
the reader, so each row must carry one.
"""

from __future__ import annotations

import re

import pytest
from django.conf import settings

from core.exceptions import FALLBACK_CODES
from tests.error_codes import collect_codes

DOC = (settings.BASE_DIR.parent / "docs" / "error-codes.md").read_text(encoding="utf-8")

#: Codes the envelope machinery can produce without any application raising
#: one: the status→code fallback table, plus what ``resolve_code`` names
#: directly, plus the DRF ``ErrorDetail`` codes that can reach the top level.
#: Kept as an explicit list because they exist by *convention* rather than by
#: a ``code="…"`` in the source — which is exactly why they need saying.
FRAMEWORK_CODES = frozenset(
    set(FALLBACK_CODES.values())
    | {
        "validation_error",  # resolve_code: a bare field-dict ValidationError
        "authentication_failed",  # DRF BadCredentials
        "parse_error",  # DRF JSON/Unicode decode failure
        "http_method_not_allowed",  # Django's own 405 detail code
    }
)

#: Everything after the envelope section: §1 documents the four envelope
#: *fields* in a table too (`code`, `message`, …) and those are not codes, so
#: the status check starts at the reference tables.
REFERENCE = DOC.split("## 2.", 1)[1]

#: `| `some_code` | 400 | … |` — the first cell and the status cell.
ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|\s*(\d{3})\s*\|", re.MULTILINE)

#: Codes the reader is told about, whatever their provenance.
DOCUMENTED = dict(ROW.findall(REFERENCE))


def test_the_collector_found_something():
    """If this fails the extraction is broken, not the doc — check it first."""
    assert len(collect_codes()) > 30


def test_every_source_code_is_documented():
    source = collect_codes()
    missing = sorted(code for code in source if code not in DOCUMENTED)
    assert not missing, (
        f"{missing} are raised by the backend but absent from "
        f"docs/error-codes.md (first seen at {', '.join(source[m] for m in missing)})"
    )


def test_every_documented_code_still_exists():
    known = set(collect_codes()) | FRAMEWORK_CODES
    stale = sorted(code for code in DOCUMENTED if code not in known)
    assert not stale, f"docs/error-codes.md documents {stale}, which nothing emits any more"


def test_every_documented_code_states_a_status():
    """The status is the part a client branches on first; a row without one
    is a row nobody can use."""
    # ROW only matches rows that *have* a status, so a table row written
    # without one would be missed — compare every backticked first cell in
    # the reference tables against the status-bearing ones.
    in_tables = set(re.findall(r"^\|\s*`([a-z0-9_]+)`\s*\|", REFERENCE, re.MULTILINE))
    without_status = sorted(in_tables - set(DOCUMENTED))
    assert not without_status, f"docs/error-codes.md rows without an HTTP status: {without_status}"


def test_the_doc_is_linked_from_the_docs_index():
    index = (settings.BASE_DIR.parent / "docs" / "README.md").read_text(encoding="utf-8")
    assert "error-codes.md" in index, "docs/README.md does not link the reference"


@pytest.mark.parametrize("section", ["## 2.", "## 7.", "## 8."])
def test_the_doc_covers_the_contract_machinery(section):
    """The envelope, idempotency and versioning sections are the part of the
    contract every client reads first."""
    assert section in DOC
