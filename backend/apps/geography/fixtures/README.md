# Geography fixture — `geography.json`

The official Algerian administrative map as data: **69 wilayas** and
**1,541 communes**, each with French and Arabic names. Loaded with:

```bash
python manage.py load_geography        # idempotent upsert on the `code` fields
```

## Provenance (generated 2026-10-14)

| Part | Source |
|---|---|
| 1,541 communes + the 58 pre-reform wilayas (codes 01–58) | [othmanus/algeria-cities](https://github.com/othmanus/algeria-cities) — `json/algeria_cities.json` (French names via `*_ascii`, Arabic via the non-ASCII fields) |
| 11 new wilayas (codes 59–69) | The November 2025 reform, enacted by **Law 26-06** — names cross-checked against [Wikipedia: Provinces of Algeria](https://en.wikipedia.org/wiki/Provinces_of_Algeria) |

The commune count (1,541) matches the official figure on Wikipedia; the
wilaya count (69) reflects the reform that took effect on 2025-11-16 (58
wilayas before it).

## How the reform is represented

The 11 new wilayas were carved out of nine older ones, but a machine-readable
commune-level mapping has not been published yet. Therefore:

- each new wilaya carries **its capital commune** (same name as the wilaya),
  moved from its parent wilaya — e.g. `Aflou` 03 → 59, `Messaad` 17 → 66;
- the remaining communes of the new wilayas **stay attached to the parent
  wilaya** until the official mapping is available.

When the official commune lists land, regenerate this file (keep the internal
`code` values stable — addresses reference them) and re-run the command.

## Notes

- `Commune.code` is internal (`<wilaya code><index>`); official commune
  numbering is not available in a machine-readable form.
- `latitude`/`longitude` exist on both models but are empty here: the source
  dataset does not carry coordinates. Fill them from an authoritative
  geodata source when maps arrive (Phase 29 backlog).
- `name_en` is empty by design — there is no authoritative English list, and
  the French names are what international users already read.
- `tests/test_fixture.py` locks the invariants: 69 wilayas (codes 01–69
  exactly), 1,541 communes, no duplicate commune name within a wilaya, and
  every capital-commune reassignment present.
