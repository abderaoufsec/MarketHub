# Phase 12 in-progress state (saved 2026-10-15, mid-phase)

> Temporary handoff file. Delete when Phase 12 is committed. Read this first
> to resume without re-deriving decisions.

## Goal
Phase 12 (docs/todo.md): Category tree & dynamic attributes — `Category`
(django-mptt 0.18.0, verified working with Django 6.0.1/Python 3.14),
`AttributeDefinition` per category, JSONB `attributes_json` validated against
effective definitions, `Product.category`/`Store.category` free-text/choices →
catalog FKs, dynamic posting form + filter sidebar, launch seed.

## DONE (backend, verified so far)

### New app `backend/apps/catalog/`
- `models.py` — `Category(MPTTModel)`: slug (stable contract), name_fr/ar/en,
  parent TreeForeignKey, icon, order, is_active; `display_name` (Accept-Language
  like geography), `effective_attribute_definitions()` (own + ancestors', deeper
  overrides same key, one query). `AttributeDefinition`: key (lower_snake_case),
  label_fr/ar/en, type enum (text/number/enum/boolean/year/range), required,
  filterable, unit, choices JSONB for enums, unique (category, key), `clean()`.
- `validation.py` — `validate_attributes(category, attrs)`: strict (unknown keys
  rejected, inactive defs ignored, bools strict, year 1900–2100, range
  {min,max} min<=max, enum in choices, numbers coerce from numeric strings).
  Raises `django ValidationError` — structural errors as bare messages, value
  errors as `{key: message}` (serializer nests under `attributes_json`).
- `serializers.py` — `AttributeDefinitionSerializer` (label via display_label,
  choices with per-choice localized `label`), `CategorySerializer` (recursive
  children, own defs inlined, `product_count` from annotated
  `descendant_product_count`), `CategoryMiniSerializer` ({id, slug, name}).
- `views.py` — `CategoryTreeView` GET /api/v1/catalog/categories/ (unpaginated,
  active roots, OuterRef Subquery subtree product counts, drops inactive
  children in serializer).
- `urls.py`, `admin.py` (DraggableMPTTAdmin + AttributeDefinitionInline),
  `apps.py`.
- `fixtures/categories.json` — 15 roots / 23 nodes / 45 defs (cars7, motorcycles5,
  auto-parts2, real-estate2 + apartments3/villas2/land1, phones-tablets4,
  electronics1+computers2/tv-audio1, fashion3, home-garden1, books2,
  sports-outdoors1, toys-games2, jobs4, animals2; books/language, food/beauty/
  services/miscellaneous = 0 defs). 9 legacy roots reuse stores.0005 slugs.
- `fixtures/README.md` (provenance), `management/commands/load_categories.py`
  (idempotent upsert by slug / (category,key), validates types+enum choices,
  ends with `Category.objects.rebuild()`), `tests/test_fixture.py` (11 file-
  level tests, all pass).

### Migrations (applied to dev DB ✓)
- `catalog/0001_initial`
- `stores/0005_store_category_fk` — RemoveIndex stores_category_newest →
  RenameField → AddField FK (PROTECT, null) → RunPython creates the 9 legacy
  ROOTS if missing (hand-written leaf mptt fields; rebuild() heals later) and
  links stores → RemoveField → AddIndex on FK. All 7 dev stores linked ✓.
- `products/0004_product_category_fk` — same pattern; **depends on
  stores/0005** (found the ordering bug: on a fresh DB the roots must exist
  before product mapping runs); maps legacy free text by slug / slugify(name) /
  name_fr lowercase, unmatched → NULL; adds `products_attributes_gin`
  (GinIndex on attributes_json) + recreated `products_category_newest`.
- `core/settings.py`: added `"apps.catalog"` (after geography) AND
  `"django.contrib.postgres"` (required for GinIndex).
- `core/urls.py`: `path("catalog/", include("apps.catalog.urls"))`.
- Dev DB cleanup done: 8 junk products manually linked to electronics root;
  `load_categories` run (23 cats, 45 defs).

### Contract changes (backend)
- `stores/serializers.py` — StoreSerializer: `category` nested mini (read),
  `category_id` PK write, `category_label` = display_name; StoreCreateSerializer
  requires `category_id`. `Store.CATEGORY_CHOICES` deleted from model.
- `stores/views.py` — seller analytics breakdown groups `category__slug`
  (NULL → "uncategorized").
- `stores/admin.py` — category_badge uses root slug → color map + name_fr.
- `products/serializers.py` — ProductSerializer + ProductListSerializer:
  `category` nested mini. ProductCreateUpdateSerializer: `category_id` write
  (active-only queryset), required-on-create via `validate()`, `attributes_json`
  validated with `validate_attributes` (Django ValidationError caught → nested
  under `attributes_json`); re-filing without attributes revalidates stored
  attrs against the new category.
- `products/views.py` — `apply_catalog_filters(queryset, query_params)`:
  `?category=<slug>` → subtree (`get_descendants(include_self=True)`, unknown →
  empty page), `?attr_<key>=` exact (boolean "true"/"false" mapped), numeric
  `?attr_<key>_min/_max` via `Cast(KeyTextTransform(...), DecimalField())`,
  RANGE = overlap bounds; unknown/non-filterable keys → 400 ValidationError.
  filterset_fields now `["is_available"]` only; search_fields = category
  name_fr/ar/en; all product querysets `select_related("store", "category")`.
- `tests/factories.py` — `CategoryFactory` (django_get_or_create slug),
  `AttributeDefinitionFactory`, `default_category()` (get_or_create
  electronics root), Store/ProductFactory use `LazyFunction(default_category)`.
- `apps/users/management/commands/seed_e2e.py` — `call_command("load_categories")`,
  store→electronics, product→phones-tablets, refreshes existing rows.
- Tests updated: `apps/stores/tests/test_stores.py` (payload category_id,
  unknown-category test uses category_id=999999), `apps/products/tests/
  test_products.py` (CategoryFactory instances, payload category_id).

## CURRENT FAILURES (last subset run: 95 passed, 3 failed)
`python -m pytest apps/stores apps/products tests/test_idor.py
tests/test_query_performance.py apps/users/tests/test_localization.py`

1. `tests/test_query_performance.py::test_store_list_20_rows_is_constant`
   — 21 queries vs budget 4. **Fix: `select_related("category")` in
   `_stores_with_product_counts()` (apps/stores/views.py line ~27).**
2. `tests/test_query_performance.py::test_cart_with_ten_lines_is_constant`
   — CartItemSerializer embeds `ProductListSerializer` (nested category) →
   per-line category query. **Fix: `select_related("category")` on the product
   lookups in apps/orders/views.py (lines ~47, ~64, ~148 `_cart_with_items`/
   `_annotated_product` and the order list/detail querysets ~270–322).**
3. `tests/test_query_performance.py::test_store_analytics_is_routed_and_
   aggregates_real_rows` — assertion still expects old string categories.
   **Fix: update the test to expect slugs (`category__slug` / "uncategorized").**

## NEXT STEPS (in order)
1. Apply the 3 fixes above → re-run subset → full suite:
   `python -m pytest -q` (watch: `tests/test_locale.py::
   test_every_raised_message_is_translated` failed in the FIRST full run —
   my new untranslated strings may need gettext `_()` in
   products/serializers.py ["A category is required."] and catalog/validation.py
   messages, or they pass; re-check. `apps/users/tests/test_localization.py`
   passed in the subset.)
2. `python manage.py spectacular --file /dev/null` + `ruff check .` +
   `ruff format .` (ruff reformats files automatically in this env — re-read
   after long runs).
3. WRITE `backend/apps/catalog/tests/test_catalog.py` (still missing!): model
   tree ops (get_descendants/ancestors, effective defs inheritance + deeper
   override, display_name ar/fr), validation unit tests (all 6 types, required,
   unknown key, enum, range min>max, year bounds, bool strictness, inactive
   ignored, no-category-with-attrs), API: GET /catalog/categories/ shape +
   Accept-Language localization (fr vs ar `name`), product create with
   category_id + attributes_json errors (400 details nested), subtree filter
   (?category=parent shows child products), attr exact + min/max + range
   overlap + unknown key → 400, inactive category_id rejected.
4. Update `backend/create_test_data.py` (dev script, lines ~58/109 still send
   "category": "Electronics" strings).
5. Re-run `python manage.py load_categories` sanity + regenerate spectacular.
6. **Frontend** (not started): `src/lib/catalog.js` (fetch tree, cache by
   locale like geography.js), `components/common/CategoryPicker.js`,
   dynamic attribute form component (renders by definition type, labels from
   server `label` field), seller product create/edit pages (category picker +
   dynamic fields → `category_id` + `attributes_json`), store setup form
   (`category_id`), products page filter sidebar (category select + attr
   filters wired to `?attr_*`), ProductCard/detail `product.category` now
   object → `product.category?.name`. Update unit tests + e2e specs
   (post-listing spec must pick a category first; e2e fixtures pin locale en).
7. Full frontend gates: lint/format/test/`next build`/e2e 5/5.
8. Docs: docs/todo.md Phase 12 checkboxes + completion note + status line
   ("Phases 0–12 ✅ · backend NNN tests · frontend NNN unit + 5 e2e"), README
   (8 apps, routes, counts), delete this file, commit.

## Environment notes (from earlier phases, still true)
- `python -m pytest` (NOT manage.py test). Coverage gate 60% on full run.
- PowerShell decodes as cp1252 → Arabic shows mojibake in console; verify via
  codepoints or `-Encoding UTF8` files.
- mptt admin: DraggableMPTTAdmin method is `indented_title` (not indented_name).
- Backend test count before Phase 12: 403 + 1 xfail.
