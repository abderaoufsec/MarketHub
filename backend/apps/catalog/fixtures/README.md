# Catalog fixture — `categories.json`

The launch category tree as data: **15 root categories** (23 nodes with
children) and **45 attribute definitions** in French and Arabic, each with the
enums the posting form and the filter sidebar render. Loaded with:

```bash
python manage.py load_categories    # idempotent upsert on slugs + (category, key)
```

## Provenance (curated 2026-10-15)

Hand-curated for Phase 12, modeled on the top-level taxonomy of the Algerian
classifieds market (Ouedkniss's category tree) and trimmed to what the
platform launches with. It is **not** a copy of any site's full tree:

| Part | Notes |
|---|---|
| 9 legacy roots (`electronics`, `fashion`, `home-garden`, `books`, `sports-outdoors`, `toys-games`, `food-beverages`, `beauty-health`, `miscellaneous`) | Same slugs the `stores.0005` data migration created, so existing stores keep their category after the FK conversion |
| 6 launch roots (`vehicles`, `real-estate`, `phones-tablets`, `jobs`, `services`, `animals`) | New in Phase 12, covering the todo's example attribute sets |
| Children (`cars`, `motorcycles`, `auto-parts`, `apartments`, `villas`, `land`, `computers`, `tv-audio`) | The three-deep demo of inheritance: `apartments` inherits `deal_type` + `area` from `real-estate` |
| 45 attribute definitions | Phase 12 examples from the todo: vehicles (brand, model, year, km, fuel, gearbox, papers), real estate (type, rooms, m², floor, deal type), phones (brand, storage, condition), jobs (contract, experience, salary) |

Phase 29 owns the full taxonomy expansion. When it lands, extend this file —
the loader upserts, so growing the tree never touches products that reference
existing rows.

## Notes

- `slug` is the stable contract: it appears in API payloads and in the
  `?category=<slug>` / `?attr_<key>=` filters. Never rename one casually.
- `label_fr` is the guaranteed-complete language; `label_ar`/`label_en` ride
  along (same convention as the geography fixture).
- Enum `value`s are machine data (`"petrol"`, `"cdi"`); labels are UI only.
- New wilaya-style rule of thumb: roots that predate Phase 12 keep the names
  `stores.0005` gave them, so the migration and this file never disagree.
- `tests/test_fixture.py` locks the invariants: unique slugs, every child
  references a known parent, enums carry choices, no duplicate key within a
  category, and Arabic/French labels everywhere.
