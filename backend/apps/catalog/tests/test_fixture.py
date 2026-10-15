"""The committed catalog fixture must be internally consistent (Phase 12).

The fixture *is* the product for this phase: it decides which forms the
listing wizard renders and which filters the sidebar shows, and unlike code
nothing fails at import time when a choice value is mistyped. These tests are
a file-level tripwire — they run without a database and fail the moment
someone edits `categories.json` by hand without checking.

Counts are pinned deliberately, exactly like `geography/tests/test_fixture.py`
pins 69 wilayas / 1,541 communes: the launch tree is curated data of record,
not something that should drift silently. Bump them in the same commit that
intentionally grows the tree (Phase 29 will).
"""

import json
import re
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "categories.json"

VALID_TYPES = {"text", "number", "enum", "boolean", "year", "range"}
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# The nine roots stores.0005 (Phase 12) created for the legacy store choices.
LEGACY_ROOT_SLUGS = {
    "electronics",
    "fashion",
    "home-garden",
    "books",
    "sports-outdoors",
    "toys-games",
    "food-beverages",
    "beauty-health",
    "miscellaneous",
}


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def flatten(rows=None):
    """Every category node in the tree, depth-first."""
    if rows is None:
        rows = load_fixture()["categories"]
    for row in rows:
        yield row
        yield from flatten(row.get("children", []))


def definitions():
    for row in flatten():
        for definition in row.get("attribute_definitions", []):
            yield row, definition


def test_launch_tree_counts_are_pinned():
    rows = load_fixture()["categories"]
    assert len(list(flatten(rows))) == 23
    assert len(list(definitions())) == 45


def test_the_nine_legacy_store_roots_are_present():
    roots = {row["slug"] for row in load_fixture()["categories"]}
    assert roots >= LEGACY_ROOT_SLUGS


def test_slugs_are_unique_across_the_whole_tree():
    slugs = [row["slug"] for row in flatten()]
    assert len(slugs) == len(set(slugs))


def test_definition_keys_are_unique_within_a_category():
    for row in flatten():
        keys = [definition["key"] for definition in row.get("attribute_definitions", [])]
        assert len(keys) == len(set(keys)), f"duplicate key in {row['slug']}"


def test_keys_are_lower_snake_case():
    for _, definition in definitions():
        assert KEY_PATTERN.match(definition["key"]), definition["key"]


def test_types_are_valid_and_enums_carry_choices():
    for row, definition in definitions():
        assert definition["type"] in VALID_TYPES, (
            f"{row['slug']}.{definition['key']}: {definition['type']}"
        )
        choices = definition.get("choices", [])
        if definition["type"] == "enum":
            assert choices, f"{row['slug']}.{definition['key']} is an enum without choices"
        else:
            assert not choices, f"{row['slug']}.{definition['key']} is not an enum but has choices"


def test_choice_values_are_unique_non_empty_strings():
    for row, definition in definitions():
        values = [choice["value"] for choice in definition.get("choices", [])]
        assert all(isinstance(value, str) and value.strip() for value in values), (
            f"{row['slug']}.{definition['key']}"
        )
        assert len(values) == len(set(values)), f"{row['slug']}.{definition['key']}"


def test_every_row_carries_french_and_arabic():
    for row in flatten():
        assert row["name_fr"].strip() and row["name_ar"].strip(), row["slug"]
        for definition in row.get("attribute_definitions", []):
            assert definition["label_fr"].strip(), f"{row['slug']}.{definition['key']}"
            assert definition["label_ar"].strip(), f"{row['slug']}.{definition['key']}"


def test_every_enum_choice_labels_all_three_languages():
    for row, definition in definitions():
        for choice in definition.get("choices", []):
            for language in ("label_fr", "label_ar"):
                assert choice.get(language, "").strip(), (
                    f"{row['slug']}.{definition['key']}.{choice['value']} missing {language}"
                )


def test_required_and_filterable_are_booleans():
    for row, definition in definitions():
        for field in ("required", "filterable"):
            assert isinstance(definition[field], bool), f"{row['slug']}.{definition['key']}.{field}"


def test_the_todo_example_attribute_sets_are_seeded():
    """docs/todo.md Phase 12 lists four example sets; all four ship."""
    by_slug = {row["slug"]: row for row in flatten()}
    keys = {
        slug: {definition["key"] for definition in row.get("attribute_definitions", [])}
        for slug, row in by_slug.items()
    }
    assert {"brand", "model", "year", "km", "fuel", "gearbox", "papers"} <= keys["cars"]
    assert {"rooms", "floor"} <= keys["apartments"]
    assert {"brand", "storage", "condition"} <= keys["phones-tablets"]
    assert {"contract", "experience", "salary"} <= keys["jobs"]
