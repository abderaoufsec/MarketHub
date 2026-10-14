"""The committed geography fixture must match the *official* counts.

Algeria's wilaya count has changed twice in recent history (48 → 58 in 2019
→ **69** with Law 26-06, effective 2025-11-16), which is exactly why
docs/todo.md Phase 11 insists the data be verified rather than assumed. These
tests are a file-level tripwire: they run without a database and fail the
moment someone regenerates the fixture from a stale source.
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "geography.json"

# code -> capital commune that the 2025/2026 reform moved to the new wilaya.
REFORM_CAPITALS = {
    "59": "Aflou",
    "60": "Barika",
    "61": "El Kantara",
    "62": "Bir-El-Ater",
    "63": "El Aricha",
    "64": "Ksar Chellala",
    "65": "Ain Oussera",
    "66": "Messaad",
    "67": "Ksar El Boukhari",
    "68": "Bou Saada",
    "69": "Labiodh Sidi Cheikh",
}


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_wilaya_codes_are_exactly_the_official_69():
    codes = [row["code"] for row in load_fixture()["wilayas"]]
    assert codes == [f"{i:02d}" for i in range(1, 70)]


def test_commune_count_is_the_official_1541():
    assert len(load_fixture()["communes"]) == 1541


def test_every_commune_references_a_known_wilaya():
    data = load_fixture()
    codes = {row["code"] for row in data["wilayas"]}

    unknown = {row["wilaya_code"] for row in data["communes"]} - codes
    assert unknown == set()


def test_commune_names_are_unique_within_a_wilaya():
    seen = set()
    for row in load_fixture()["communes"]:
        key = (row["wilaya_code"], row["name_fr"].casefold())
        assert key not in seen, f"duplicate commune {key}"
        seen.add(key)


def test_wilaya_and_commune_names_carry_arabic():
    data = load_fixture()

    assert all(row["name_ar"].strip() for row in data["wilayas"])
    assert all(row["name_ar"].strip() for row in data["communes"])


def test_reform_capitals_belong_to_their_new_wilaya():
    by_wilaya = {}
    for row in load_fixture()["communes"]:
        by_wilaya.setdefault(row["wilaya_code"], set()).add(row["name_fr"])

    for code, capital in REFORM_CAPITALS.items():
        assert capital in by_wilaya[code], f"{capital} missing from new wilaya {code}"
