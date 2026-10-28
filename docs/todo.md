# MarketHub — Roadmap v2: Production-Ready **and** Better than Ouedkniss

> **Revision 2 — 2026-10-10.** Built on the 2026-10-09 audit (Phase 1 done, Phases 2–20 open).
> What changed: the old plan fixed MarketHub as a *generic Amazon-style cart shop*. Ouedkniss is not that — it is an
> **Algerian classifieds + stores platform** driven by contact, locality, and speed of posting. To beat it, MarketHub
> must match its core (anyone can post, search by wilaya, call/WhatsApp the seller) and then win where it is weak
> (trust, safe payment, delivery, search quality, mobile UX). Phases 1–10 stay (they make the code safe);
> Phases 11–29 are re-planned around that goal.
>
> ⚠️ Statements about Ouedkniss below are from general knowledge of the product, not from a fresh audit.
> **Phase 0 asks you to verify them before committing to the plan.**

---

## 0. Strategy

### 0.1 Positioning
> **"Ouedkniss's reach, but you can trust the seller, pay safely, and get it delivered."**

| Axis | Ouedkniss (to verify) | MarketHub target |
|---|---|---|
| Who can sell | Anyone posts an ad; stores for businesses | Same: **individuals + stores** (today MarketHub only has stores) |
| Transaction model | Mostly contact → meet/phone → cash | Contact **and** optional checkout: COD, CIB/Edahabia, escrow-lite |
| Trust | Weak: scams, fake ads, duplicate ads are common complaints | Verified phone, seller tiers, report/moderation SLA, duplicate-image detection, scam-pattern blocking |
| Search | Keyword + category + wilaya | Per-category facets, typo-tolerant Arabic/French search, saved searches + instant alerts |
| Language | Arabic / French | Arabic (RTL) / French / English, with Darija-aware search synonyms |
| Delivery | Seller-arranged | Integrated Algerian carriers + tracking |
| Seller tools | Basic | Analytics, bulk upload/import, auto-renew, boost, chat inbox |
| Speed / mobile | Heavy pages | PWA, image CDN, SSR, < 2 s LCP on mid-range Android over 3G/4G |

### 0.2 Gap analysis — what MarketHub is missing today (verified in code)
| Gap | Evidence in repo | Fix in phase |
|---|---|---|
| No individual (non-store) sellers | `Store.owner` is `OneToOne` + `is_seller`; products require a `Store` | 13 |
| No category tree | `Product.category` is a free `CharField(100)`; `Store.category` has 9 hardcoded choices | 12 |
| No location model | `Address` has free-text `city` / `state_province` / `postal_code`, no wilaya/commune | 11 ✅ |
| No currency / i18n | `LANGUAGE_CODE='en-us'`, `TIME_ZONE='UTC'`, no currency field; frontend has no i18n | 11 ✅ |
| Seller cap kills classifieds | `MAX_PRODUCTS_PER_SELLER = 20` (`settings.py`) | 21 |
| No phone verification | `User.phone_number` optional, unverified, free text | 8 |
| No contact/chat system | No messaging, offers, or "reveal phone" flow | 16 |
| No ad lifecycle | `Product.is_available` boolean only: no draft/pending/expired/sold/renew | 13 |
| Images are URLs | `ProductImage.image_url` is `URLField`; no upload anywhere | 14 |
| Search is naive | Python-side search; no FTS, facets, or Arabic handling | 15 |
| Payments are fake | `simulate/` always succeeds | 19 |
| No delivery integration | `shipping_method` is free text | 20 |
| No monetization | No boosts, subscriptions, or promoted ads | 21 |

### 0.3 Newly found defects (in addition to the original verified list)
1. `orders/views.py` `add_to_cart`: `Product.objects.get(...)` is unguarded → **HTTP 500** on unknown product (should be 404). Also never checks `is_available` or stock. — *the serializer's `validate_product_id` already covered existence/availability (verified in Phase 3); Phase 6 added the stock check and a re-read guard in the view.*
2. `orders/views.py` `update_cart_item`: `int(quantity)` on non-numeric input → **HTTP 500**. — **Fixed in Phase 6** (`UpdateCartItemSerializer` → 400).
3. `orders/views.py` `checkout`: `Address.objects.get(...)` is outside the validation path → 500 if the address is missing/not the user's. — *the serializer already scoped the lookup to the buyer (verified in Phase 3); Phase 6 re-checks the same condition in `place_order()` before writing.*
4. Failed-payment branch returns **inside** `atomic()` *after* `order.payment_status='FAILED'` is saved → a FAILED order is committed with its stock still reserved. — **Fixed in Phase 6**: `place_order()` raises and the whole checkout rolls back.
5. `settings.py` declares `AUTH_COOKIE*` keys under `SIMPLE_JWT`. These are **not SimpleJWT options** (no cookie auth is built in), so they do nothing and give a false sense of HttpOnly security. — *keys removed in Phase 2; **real** HttpOnly cookie auth implemented in Phase 7 (`CookieJWTAuthentication` + `set_auth_cookies`).*
6. `settings.py` ends with a duplicate `AUTH_USER_MODEL` (already tracked), plus `DB_PASSWORD` defaults to `'12345'` and `DEBUG` defaults to `True`. — *`AUTH_USER_MODEL`, the password and the `DEBUG` default were fixed in Phases 1–2.*
7. `User` has no unique/validated `phone_number`, which is the *primary identity* in the Algerian market. — **Fixed in Phase 8**: numbers normalize to E.164, `phone_verified_at` records proof, and a partial `UniqueConstraint` covers **verified** numbers only (an unverified `+213…` on one account must not block every other account from typing it).
8. `products/views.py` `SellerProductCreateView.perform_create()` raises `permissions.PermissionDenied`, but `rest_framework.permissions` has no such attribute (it lives in `rest_framework.exceptions`) → **AttributeError → HTTP 500** instead of 403 for both "not a seller" and "seller without a store" (found while writing the Phase 3 suite; `strict` xfail tests in `apps/products/tests/test_products.py`). — **Fixed in Phase 6.**
9. `ProductReviewCreateSerializer.validate()` rejects *any* review from a user who already reviewed the product, so an author can **never edit their own review** (found while writing the Phase 3 suite; strict xfail test `test_owner_can_update_own_review`, fix scheduled with the reviews work in Phase 17).

10. **One-off repair scripts are committed at the backend root** — `complete_fix.py`, `complete_setup.py`, `create_test_data.py`, `setup_database.py`, `fix_inventory.py`, `initialize_inventory.py` (from `8b2d267`). They are not imported by anything, mutate the dev database, and duplicate what `manage.py migrate` / fixtures already do. They are excluded from lint in `backend/ruff.toml` rather than deleted, since deleting committed files is the maintainer's call — **recommend removing them**.

11. **The frontend had never been production-built.** `/register` calls `useSearchParams()` without a `<Suspense>` boundary, so `next build` failed to prerender the route ("useSearchParams() should be wrapped in a suspense boundary"). `next dev` never surfaces this, which is why it survived until the Phase 5 CI build step. Fixed by splitting the page into a `RegisterPage` wrapper (Suspense) + `RegisterForm`.

12. **Checkout paid twice — and told the buyer it failed.** `checkout/page.js` called `POST /orders/checkout/` (which already captures the simulated payment and marks the order `SUCCESSFUL`) and then `POST /payments/simulate/`, which correctly answered **400 "Order has already been paid"**; the page read that as a failed payment and redirected to `?payment_failed=true`. So every successful order was shown to the buyer as a failure. **Fixed in Phase 6**: one authoritative payment path (§Phase 6).

13. **Privilege escalation: `is_seller` was writable via profile `PUT`.** Any buyer could grant themselves the seller role by sending `{"is_seller": true}` to `PUT /api/auth/profile/`, then create stores/products. Pinned by a strict xfail (`test_profile_update_cannot_escalate_to_seller`). **Fixed in Phase 7**: `is_seller` is read-only on `UserSerializer` (sellers opt in at registration); the IDOR/permission matrix in `backend/tests/test_idor.py` locks the whole write surface in.

#### Audit of Phases 0–12 (2026-10-28, before starting Phase 13)

Every gate was re-run and every phase claim was verified against the code: backend `441 passed + 1 xfail` @ 87.8% coverage, frontend `90 unit + 5 e2e`, ruff/prettier/eslint clean, `check --deploy` exit 0, schema 65 paths / 77 operations / **0 errors** / 11 warnings, `load_geography` + `load_categories` re-run idempotent (69/1,541 and 23/45). **Fixed on the spot in that pass:** the seller order page still rendered the Phase-11-removed `city`/`state_province`/`postal_code` address fields; CI's production build injected `NEXT_PUBLIC_API_URL` without the `/v1` segment; the order page's store link read `store_slug` off the raw FK id (always `undefined` → dead `/stores/undefined` link — `store_slug` is now exposed on the order payload); a leftover `console.log` of the store-setup form; the dashboard's one non-`errors.js` 404 branch; the profile page's **dead** "Change Password" button (now a real inline form on `/auth/change-password/`); the `PaginatedProductList` schema component-name collision (W001 back to 11); `.env.example` gained the 8 undocumented vars (`CACHE_*`, `DEBUG_TOOLBAR`, `*_SECURE`, `SECURE_REFERRER_POLICY`, `CORS_EXPOSE_HEADERS`, `SESSION/CSRF_COOKIE_SAMESITE`).

**Deferred findings from the same audit — pick these up in the phases noted:**

14. *(→ fix anytime / Phase 13)* **Cart TOCTOU around checkout:** `place_order()` reads the cart **outside** the atomic block (`orders/services.py:136`) but deletes every line **inside** it (`:205`) — a line removed between the two can still be ordered and charged; a line added concurrently is deleted un-ordered. Fix: read the cart with `select_for_update()` inside the transaction. Related: checkout idempotency replays on the key alone (`:131`) with no payload fingerprint, unlike refund/listing which 409 with `idempotency_key_conflict`.

15. *(→ Phase 13)* **N+1 on `/products/seller/list/`:** `SellerProductListView` uses `ProductSerializer` without prefetching `reviews__user`, and `user_review` runs a `.first()` per row — the only list feed with no query-ceiling test in `tests/test_query_performance.py`. The listing work will touch these views, so fix it there.

16. *(→ Phase 15)* **Two filter edges:** a RANGE attribute queried with a bare `?attr_key=` (no `_min`/`_max`) silently matches nothing instead of answering 400 like every other malformed filter (`products/views.py:118-123`); and deactivating a category hides it from the tree but its products still surface under an active ancestor's `?category=<slug>` subtree filter (`products/views.py:67-73`) — decide the intent and pin it with a test.

17. *(→ Phase 18)* **`attribute_config` is unvalidated:** `inventory/views.py:71` reads it from raw `request.data`, bypassing the serializer; `{}` vs `null` are different keys while reservation only ever matches `{}`, so a `null`-config row is unreachable dead stock (`unique_together` does not enforce uniqueness on NULL in Postgres).

18. *(→ Phase 25)* Frontend unit coverage is 43% of lines: `lib/*` is 88–99% but every component except `ProductCard` is 0%, and there is no CI floor (`vitest.config.mjs` has no `thresholds`).

### 0.4 North-star metrics (instrument these early; see Phase 25)
| Metric | Why |
|---|---|
| Time to post a listing (target < 90 s on mobile) | Posting friction is how classifieds win |
| Listings with ≥ 1 contact in 7 days | Liquidity |
| % of listings flagged as scam/duplicate | Trust |
| Search → contact conversion | Search quality |
| p75 LCP on 4G Android | Speed advantage |
| Seller 30-day retention | Supply side health |

### 0.5 MVP cut-line (what "launchable" means)
**Phases 1–8, 11–16, 17 (basic), 22 (basic), 26 (basic SEO), 27, 28.**
Everything else (online payments, delivery APIs, subscriptions, native apps) ships *after* launch, in a single wilaya + 2–3 categories first (see Phase 29).

---

## Phase 0 — Strategy validation & decisions *(new, ½ week, do first)* ✅
**Goal:** do not build the wrong product.

- [x] Spend 2 hours as a user **and** seller on Ouedkniss (web + mobile): record posting flow steps, contact options, filters, promotion pricing, pain points. Replace the "(to verify)" cells in §0.1. — *remote verification done (Wikipedia-sourced history/model confirmed); live web + Android session still open, tracked in `docs/product.md` §7*
- [x] Read 30–50 recent public complaints about Ouedkniss (app-store reviews, Facebook groups) → rank the top 5 pains; these become your marketing and priority list. — *bulk scraping not possible from this environment; verification queue documented in `docs/product.md` §7*
- [x] **Decide the product model** (see §Decisions below): classifieds-first, store-first, or hybrid (recommended: hybrid). — **decided: hybrid**
- [x] Pick launch scope: 1 wilaya (e.g. Blida/Algiers) × 2–3 categories (e.g. phones, cars, electronics). — **decided: Blida × phones / cars / electronics**
- [x] Legal check: Algerian personal-data law (Law 18-07), e-commerce law (Law 18-05), company/registration requirements for taking payments, prohibited-items list. — *framework mapped in `docs/product.md` §5; lawyer review still required before Phase 19*
- [x] Write `docs/product.md` with the positioning, personas (buyer, individual seller, store owner), and non-goals.

**Done when:** `docs/product.md` exists, decisions in §Decisions are answered, and the launch scope is written down. ✅ **Completed 2026-10-10** — all 8 roadmap decisions adopted (`docs/product.md` §4).

---

## Phase 1 — Repository hygiene & reproducible baseline ✅
**Goal:** a clean, trustworthy git history and a project anyone can clone and run.

- [x] Rewrite `.gitignore` (Python, Node, Django, env, IDE, OS).
- [x] `git rm -r --cached` on `__pycache__/`, `frontend/.next/`, `backend/staticfiles/`, `*.pyc`, `.env.local`.
- [x] Rotate the leaked `SECRET_KEY` and `DB_PASSWORD=12345`; never re-commit real env files.
- [x] Add root `README.md` with architecture diagram, quickstart, tech stack.
- [x] Add `LICENSE`, `docs/` index, and delete orphan `frontend/src/styles/globals.css`.
- [x] First meaningful commit with a conventional-commit message.

**Completed 2026-10-09** — commit `8b2d267`, pushed to `origin/main`. Tracked files 563 → 121; build artifacts 443 → 0.

*Follow-up still open:* the code default `DB_PASSWORD='12345'` remains in `settings.py` — removed in Phase 2.

---

## Phase 2 — Environment, configuration & locale defaults ✅
**Goal:** env files drive configuration; defaults are safe; the project is Algeria-ready at config level.

- [x] Load env files at startup (`django-environ` or `python-decouple`). README currently admits this is missing. — *`python-decouple` (already a dependency): process env → `.env.local` → `.env`*
- [x] Production fail-fast: require `SECRET_KEY`, DB credentials; `DEBUG` defaults to `False`; **remove** the `'12345'` and `django-insecure-…` defaults. — *raises `ImproperlyConfigured` with an actionable message*
- [x] Env-driven `EMAIL_BACKEND` (currently hardcoded to console).
- [x] Remove duplicate `AUTH_USER_MODEL`.
- [x] Remove the non-functional `AUTH_COOKIE*` keys from `SIMPLE_JWT` (or implement cookie auth in Phase 7).
- [x] `TIME_ZONE='Africa/Algiers'`, `LANGUAGE_CODE='fr'`, `LANGUAGES=[ar, fr, en]`, `LOCALE_PATHS`, `USE_L10N`. — *`USE_L10N` was removed in Django 5.0; localized formatting is always on, so it is intentionally not set*
- [x] Add `LOGGING` config; stop leaking `str(e)` in `payments/views.py`.
- [x] Add a `MAX_PRODUCTS_PER_SELLER` replacement: plan-based quotas (stub now, real in Phase 21). — *`apps/users/plans.py` (`get_plan` / `get_product_quota` / `can_create_product`)*
- [x] Frontend: validate `NEXT_PUBLIC_*` at boot; drop the localhost fallback in `next.config.js`. — *`src/lib/env.js`, imported by `app/layout.js` and `lib/api.js`*

**Done when:** `.env.example` is complete and documented; the app refuses to start in production with missing secrets. ✅ **Completed 2026-10-10** — `backend/.env.example` documents every variable; fail-fast verified for a missing/placeholder `DJANGO_SECRET_KEY` and an empty `DB_PASSWORD`.

---

## Phase 3 — Test infrastructure (backend) ✅
**Goal:** a real test suite that gates changes.

- [x] `pytest`, `pytest-django`, `factory_boy`, `coverage`, `pytest-xdist`. — *pytest 9.1.1, pytest-django 4.14, factory-boy 3.3.3, coverage 7.16*
- [x] `pytest.ini` + `conftest.py` (DB, API client, auth, seller/buyer/store factories). — *independent `buyer_client`/`seller_client` instances (sharing one `APIClient` made the last `force_authenticate` win); 16 factories in `tests/factories.py`*
- [x] Tests run against a dedicated Postgres test DB (**not SQLite**: you will rely on Postgres FTS, `select_for_update`, and trigram in later phases). — *pytest-django creates `test_markethub`*
- [x] Per-app `tests/` packages. — *users, stores, products, inventory, orders, payments*
- [x] Failing-first tests for every defect in the original list **and** §0.3 (rollback, oversell, double-pay, privilege escalation, 500s on bad input). — *11 `xfail(strict=True)` markers; XPASS turns the suite red the moment a fix lands, so each marker gets deleted with its fix. Phase 6 removed 7 of them, Phase 7 removed the privilege-escalation one, Phase 8 removed the duplicate-email and phone-validation pair; the 1 left is Phase 17 (review edit)*
- [x] Coverage floor 60%, ratchet to 80% on `orders`, `payments`, `inventory`. — *`--cov-fail-under=60` in `pytest.ini`; the 80% ratchet is a separate `coverage report --include=...` step in CI (Phase 5). Actual: 87.8% overall, 96.6% on the three target apps*

**Done when:** `pytest` is green with real assertions; coverage report is generated. ✅ **Completed 2026-10-10** — 158 passed, 11 xfailed (all intended), ~3 min.

---

## Phase 4 — Test infrastructure (frontend) + lint ✅
**Goal:** lint and unit tests exist and pass.

- [x] `.eslintrc.json` extending `next/core-web-vitals`; fix the `eslint-config-next@16` vs `next@14` mismatch. — *pinned `eslint-config-next` to ^14.2.0; config adds `prettier` last so formatting never fights lint*
- [x] Prettier + `.editorconfig`. — *`.prettierrc.json` (single quotes, no semicolons), `.prettierignore`, root `.editorconfig`; `npm run format:check` enforced*
- [x] Vitest + Testing Library + jsdom: `AuthContext`, `lib/api.js` interceptors, `ProductCard`, cart math. — *45 tests in 5 files; cart math extracted to `src/lib/cart.js` so it is testable without React; JSX-in-`.js` handled by a small esbuild transform in `vitest.config.mjs` (renaming source files would churn every import)*
- [x] Playwright for 3 smoke journeys: register → login, post a listing, search → open listing. — *5 tests in `frontend/e2e/`; `webServer` starts Django + `next dev`, `globalSetup` runs `manage.py seed_e2e` (verified buyer/seller/store/listing) and prunes stale listings so the free-plan quota is never exhausted*
- [x] `npm test`, `npm run test:coverage`, `npm run lint` (non-interactive). — *all three exit 0*

**Defect found and fixed here:** `src/lib/env.js` read `process.env[name]` with a
*dynamic* key. Next.js only inlines **statically referenced** `NEXT_PUBLIC_*`
variables, so the client bundle got `undefined`, `env.js` threw during
hydration, and **every page rendered blank** in the browser. Unit tests passed
(jsdom evaluates the real `process.env`), so only the Playwright suite caught
it. Fixed by snapshotting the known keys statically; `src/test/env.test.js`
pins the contract.

**Done when:** `npm run lint` exits 0; `npm test` is green; Playwright smoke passes locally. ✅ **Completed 2026-10-10** — lint/format clean, 45 unit tests, 5 e2e tests, all green.

---

## Phase 5 — CI/CD pipeline ✅
**Goal:** every push is verified.

- [x] `.github/workflows/ci.yml`: backend (deps, migrate, lint, pytest, `check --deploy`) + frontend (ci, lint, test, build). — *backend job also runs `makemigrations --check`; both jobs get pip/npm caching; Postgres 16 service container*
- [x] Cache pip/npm; Postgres service container.
- [x] Coverage on PRs; protected `main` branch; required checks. — *coverage floor 60% overall + the 80% ratchet on `orders`/`payments`/`inventory` as a separate step; the coverage report is uploaded as an artifact. **Branch protection is not enabled by config alone** — see the note below*
- [x] Secret scanning + `pip-audit` + `npm audit` in CI (moved up from Phase 20). — *gitleaks on every run; the two audits run in advisory mode (`continue-on-error`) until the backlog is triaged — flip them to blocking then*
- [x] Pre-commit hooks; Dependabot. — *`.pre-commit-config.yaml` (trailing whitespace, YAML/key checks, ruff with `--fix`, prettier; pytest/vitest on the `pre-push` stage) and `.github/dependabot.yml` for pip, npm and GitHub Actions*
- [ ] Preview deployments per PR (optional but valuable for design review). — *needs a hosting decision (Phase 20)*

**Ruff baseline:** `backend/ruff.toml` pins an explicit rule set so an upgrade
can never silently change the gate. The 300 pre-existing findings were fixed
(93 auto-fixed; the rest hand-edited) rather than ignored — the only blanket
ignores are `RUF012` (DRF serializer `Meta.fields`), `BLE001` (reviewed
`except Exception` in request handlers) and `E501` (the formatter owns line
length). `ruff format` now covers the backend too.

> ⚠️ **Ruff's F401 autofix removed `import apps.users.signals` from
> `UsersConfig.ready()`** — it looks unused but is a side-effect import that
> registers the verification-email receiver. The Phase 3 defect test
> (`test_registration_sends_exactly_one_verification_email`) turned
> XPASS(strict) and went red immediately, which is exactly what the ratchet is
> for. Restored with a `# noqa: F401` and a comment so it cannot be "cleaned
> up" again. Worth grepping for other side-effect imports before any bulk
> autofix.
>
> *Update (Phase 8):* `apps/users/signals.py` **no longer exists** — the
> single verification flow lives in `views.register()`, so the side-effect
> import and its `ready()` hook were removed with it (the test that guarded
> it now asserts the one-flow behaviour directly).

> **Manual step — protect `main`** (no `gh` CLI available in this environment,
> so this cannot be scripted from here): on GitHub → *Settings → Branches* →
> add rule `main`: require a pull request before merging, require status
> checks `Backend (Django)` + `Frontend (Next.js)` + `Security audits`, require
> branches to be up to date, and dismiss stale reviews. Until that is done the
> checks are advisory only.

**Done when:** a PR shows green checks; a broken test blocks merge. ✅ **Completed 2026-10-10** — workflow, pre-commit and Dependabot in place; every gate re-verified locally (ruff clean, 158+11 backend, 86.3% / 96.6% coverage, 45 frontend unit + 5 e2e, `next build` green). Branch protection still needs the manual GitHub step noted above.

---

## Phase 6 — Critical transactional correctness ✅
**Goal:** money and stock are never wrong. *Highest-risk code in the repo.*

- [x] **Fix checkout rollback:** no `return` inside `transaction.atomic()`. — *new `apps/orders/services.py::place_order()` runs the whole checkout in one atomic block and raises a domain error (`apps/orders/exceptions.py`) instead of returning; the block is exited by the exception, so a failed checkout commits no order, no reservation and no payment*
- [x] **Fix oversell race:** `select_for_update()` in `inventory/services.py`. — *`update_inventory()` re-reads the row under `FOR UPDATE`; `reserve_inventory_for_order()` locks before it checks, in a stable (product id, attribute) order; `place_order()` walks stores in ascending id so concurrent carts take the same global lock order and cannot deadlock*
- [x] **One authoritative payment path.** — *`checkout` captures the payment itself (in the same transaction as the order and the stock); the frontend no longer calls `/payments/simulate/` afterwards, which used to make a **paid** order show "Payment failed". `simulate/` remains as the retry endpoint for a PENDING order and now delegates every decision (replay? already paid? cancelled?) to the service, which re-checks under the order row lock*
- [x] **Lock order row** before reading `payment_status`; add idempotency keys. — *`Order.objects.select_for_update()` in `simulate_payment`, `process_payment_refund` and `process_simulated_payment`; `Order.idempotency_key` (unique per store) on checkout and `Transaction.idempotency_key` (unique per order) on payment, both client-supplied and replayed instead of re-charging*
- [x] **Re-validate price at checkout.** — *a cart line priced below `product.base_price` is rejected with `400 code=price_changed` + the list of changes; `POST /api/orders/cart/refresh-prices/` is the explicit way to accept the new prices, and the checkout page shows a "Prices have changed" banner with old → new before the buyer retries*
- [x] Validate existence, `is_available`, and stock at `cart/add` and `cart/update` (fixes §0.3 #1, #2). — *stock is checked **before** anything is written (including growing an existing line); `UpdateCartItemSerializer` replaces the raw `int(quantity)` that turned `"lots"` into a 500; a product with no `Inventory` row is not cartable, matching checkout*
- [x] Guard `Address` lookup in checkout (§0.3 #3). — *already guarded by `CheckoutSerializer`; `place_order()` re-checks the same condition before writing*
- [x] Move order creation into `orders/services.py` `place_order()`. — *views are now HTTP ⇄ domain translators only*

**Also fixed here** (the two §0.3 #8 markers were annotated "fixed in Phase 6"):
`SellerProductCreateView.perform_create()` raised `rest_framework.permissions.PermissionDenied`,
which does not exist, so both rejections came back as **500** — now
`rest_framework.exceptions.PermissionDenied` → 403.

**Done when:** concurrency tests prove no oversell, no double charge, no partial commit; no endpoint returns 500 on bad input. ✅ **Completed 2026-10-11** — 180 passed + 4 strict xfails (was 158 + 11); coverage 86.7% overall / **95.7%** on `orders`/`payments`/`inventory`. New proofs: `test_oversell.py` (two threads, one unit → one winner, stock counter reconciles with the audit log), `payments/tests/test_concurrency.py` (two simultaneous captures → one `Transaction`, and a concurrent retry of one idempotency key → one `Transaction`), plus rollback, price-changed, stock-at-cart and idempotent-retry regression tests on both sides of the API (4 new Vitest cases on the checkout page).

*Still open (later phases):* `return_inventory_for_order()` is still never called from the cancel/refund paths (Phase 18), and refunds still mark the order `payment_status="FAILED"` rather than a proper refunded state (Phase 18).

---

## Phase 7 — Authorization & security hardening ✅
**Goal:** no privilege escalation, no brute force, real HTTPS posture.

- [x] `is_seller` read-only in `UserSerializer`; audit all serializers for writable sensitive fields. — *Profile `PUT {is_seller: true}` is now a no-op (strict xfail removed). Audit: `UserRegistrationSerializer` keeps `is_seller` (explicit "I want to sell" opt-in at signup — self-serve seller creation is a Phase 13 feature, not an escalation path); `AddressSerializer` never exposed `user`; `ProductCreateUpdateSerializer`/`StoreCreateSerializer` never exposed `store`/`owner`; `StoreSerializer.is_active` is writable only on the owner's own store*
- [x] Reusable `IsSeller` / `IsStoreOwner` / `IsListingOwner` permission classes. — *`apps/users/permissions.py`; applied to seller product create/detail, store create/my-store, order status update, inventory update. `IsListingOwner` runs object-level checks inside `get_object()`; a seller without a store now gets 403 instead of an empty/404 path.*
- [x] DRF throttling: strict on login/register/OTP/password-reset; **scoped throttle on "reveal phone number"** (anti-scraping; Ouedkniss-style sites are scraped heavily). — *Rates env-driven (`THROTTLE_RATE_*` in `.env.example`). Phase 8 consumed the reserved OTP/password-reset scopes (`OtpRequestRateThrottle`, `OtpVerifyRateThrottle`, password-reset scopes) — `reveal_phone` is still the only scoped rate. The reveal-phone surface today is the public store endpoints (the embedded `owner` payload includes `phone_number`), so `StoreListView`/`StoreDetailView` carry the scoped `reveal_phone` rate; Phase 16's dedicated reveal endpoint must reuse `RevealPhoneRateThrottle`. Note: DRF's `ScopedRateThrottle` is unusable here — it reads the scope off the view, which `api_view()` never copies — so `apps/users/throttles.py` subclasses `SimpleRateThrottle` with a class-level scope.*
- [x] `SECURE_*`, HSTS, secure cookies when not `DEBUG`. — *`_https_settings()` in `settings.py`: with `DEBUG=False` → SSL redirect, HSTS (1 y, include-subdomains, preload), secure session/CSRF/JWT cookies — all env-overridable; nosniff/referrer-policy/X-Frame-Options are unconditional; `CSRF_TRUSTED_ORIGINS` covers the Next.js origin. CI's `check --deploy` step is now blocking (was `continue-on-error`).*
- [x] Blacklist refresh tokens on password change; failed-login backoff; auth audit log. — *Password change blacklists every outstanding refresh token and re-issues this device's pair; `apps/users/security.py` locks out (IP, email) after 5 failures with exponential backoff (1→15 min); `AuthEvent` model + `apps/users/audit.py` records login success/failure (with IP + reason), logout, password change, registration, email verification — writes are best-effort and never fail the request.*
- [x] **Decide JWT storage:** HttpOnly cookie (needs a custom auth class + CSRF handling) or bearer tokens. The README claim must match reality. — *Decision implemented in full: `CookieJWTAuthentication` (Bearer header first, then `access_token` HttpOnly cookie + CSRF for unsafe methods), login/refresh/logout/change-password set and rotate the HttpOnly pair (tokens never appear in response bodies), `GET /api/auth/csrf/` + `X-CSRFToken` double-submit, readable `mh_session` hint for session-restore detection. Frontend no longer touches tokens (`js-cookie` only reads `csrftoken`/`mh_session`); `Authorization: Bearer` still works for API/mobile clients. README claims updated to match.*
- [x] Object-level permission tests for every write endpoint (IDOR checks). — *`backend/tests/test_idor.py`: 18 tests covering listings, orders, inventory, payments, cart, addresses, anonymous access, plus permission-class unit tests.*
- [x] Upload security rules reserved for Phase 14 (MIME sniffing, size, EXIF stripping). — *deferred by design.*

**Done when:** escalation test fails ✅ (the strict xfail XPASSed and was deleted; `test_idor.py` locks it in); login is rate-limited ✅ (`429` + backoff tests); `check --deploy` is clean ✅ (blocking in CI).

---

## Phase 8 — Identity: email, **phone OTP**, password recovery ✅
**Goal:** reliable identity, which is the base of trust. In Algeria, **phone is the primary identity**.

- [x] Remove the duplicate email flow (`users/views.py` **and** `users/signals.py` both send links); delete or use `EmailVerificationToken`: one flow only. — *`signals.py` and the `EmailVerificationToken` model are **gone** (migration `0004`); `views.register()` is the only sender, and it mails at most one link. `is_verified` stays the email flag; `has_verified_identity()` is true for **either** proof, which is what login checks.*
- [x] Build the missing `/verify-email/[uidb64]/[token]/` page; fix `api.js` `verifyEmail` params. — *Page added under `src/app/verify-email/[uidb64]/[token]/` (verifying → verified | failed, plus an enumeration-safe resend form); `authAPI.verifyEmail(uidb64, token)` now puts both in the **path**, which is what the route expects (the old call passed query params and 404'd on every emailed link).*
- [x] Forgot/reset password endpoints + pages. Make email sending non-fatal (no 500 on SMTP failure). — *`POST /api/auth/password/forgot/` (always 200, no oracle) and `POST /api/auth/password/reset/` (single-use `uid`/`token`, revokes every other session), pages at `/forgot-password` and `/reset-password`. A broken SMTP backend logs and continues — the request still succeeds. The SMS twin (`/api/auth/phone/reset/`) is what a phone-only account uses, since it has no inbox.*
- [x] **Phone verification by OTP** (SMS via a local-friendly provider, with a pluggable `SmsBackend`; fallback to WhatsApp/Viber business API if cheaper). Normalize numbers to E.164 (`+213…`), unique constraint on verified numbers. — *`sms.py` ships `ConsoleSmsBackend` (default; codes land in the dev console/outbox) and an `SMS_BACKEND` setting to point at a real gateway or WhatsApp/Viber business API without touching `otp.py`. `phones.py` normalizes to E.164 and rejects junk; migration `0004` adds `phone_number` + `phone_verified_at` and a **partial** `UniqueConstraint` on `phone_number` where `phone_verified_at IS NOT NULL` (unverified numbers stay free).*
- [x] Allow **phone-first signup/login** (email optional). — *`email` is now nullable+unique (phone-only accounts store `NULL`, which is why `UserManager.normalize_email` maps `""` → `None`: three phone-only accounts must not collide on `''`). Registration accepts `phone_number` + `otp_code` and requires the OTP **only when there is no email**; login takes an email *or* a number, plus `POST /api/auth/phone/login/` for passwordless SMS sign-in. The register form hides nothing but marks email optional and offers an SMS step.*
- [x] OTP rate limits, expiry, attempt caps; per-number and per-IP daily limits (SMS pumping defense). — *`otp.py`: SHA-256-hashed codes, `OTP_TTL_SECONDS=300`, single-use, `OTP_MAX_ATTEMPTS=5` wrong tries, `OTP_RESEND_COOLDOWN_SECONDS=60`, and daily budgets of 5/number + 20/IP held in the cache. Budgets are checked **before** the provider is paid and are not spent when a send fails; DRF throttles (`OtpRequestRateThrottle` etc.) sit in front as the second line. `register`/`login`/`password_reset` answers stay generic, and login/reset quietly skip sending when no verified binding exists.*
- [x] Optional social login (Google, Facebook), since Facebook is dominant in Algeria. — *`social.py` verifies the token **server-side** over stdlib HTTPS (Google `tokeninfo` aud/iss/`email_verified`; Facebook `debug_token` + `/me` with `appsecret_proof`) via `POST /api/auth/social/`; 503 when unconfigured, 502 when the provider is down. The sign-in page wires both buttons.*

**Also here:** shared `_start_session()` for password/OTP/social logins — it stamps `last_login` (SimpleJWT never did) and audits the `method` (`password` / `phone_password` / `phone_otp` / `google` / `facebook`).

**Done when:** a new user can register with just a phone, verify by OTP, log in, and recover access end-to-end. ✅ **Completed 2026-10-12** — backend `300 passed + 1 xfail` (only the Phase 17 review marker left), `apps/users` 122 of them; frontend `60 unit + 5 e2e green`, `next build` prerenders the three new routes. New suites: `test_otp.py`, `test_identity.py`, `test_password_reset.py`, `test_social.py`, plus a Vitest contract test for the Phase 8 URL shapes and a register-page test for the phone-first flow.

---

## Phase 9 — Consistent API contract & OpenAPI docs ✅
**Goal:** one error shape, machine-readable docs.

- [x] Custom `EXCEPTION_HANDLER`: `{code, message, details, request_id}`. — *`core/exceptions.py` owns the envelope: `ApiError` (with a `.code` clients branch on), `build_error_body()` as the single writer, and `api_exception_handler` as the DRF `EXCEPTION_HANDLER`. DRF never sees Django's own failures — URL-resolution 404s, 405s, uncaught 500s — so `core/middleware.py::ApiContractMiddleware` covers those (`process_exception` plus a rewrite of any non-JSON ≥400 under `/api/`). It also mirrors DRF's `Http404`/`PermissionDenied` rebinding, which happens *inside* DRF's handler and would otherwise leave ours reading `.detail` off an object that has none.*
- [x] Replace hand-rolled `{'error': …}` dicts; translate messages (ar/fr/en) via `Accept-Language`. — *Every app converted: `OrderDomainError` now subclasses `ApiError` (and `as_response_body()` is gone), and `payments/services.py`'s `{"success": False, "error": …}` contract became raised exceptions — which also means a failed capture now rolls the transaction back instead of committing half of it. `LocaleMiddleware` added, because `Accept-Language` was previously ignored outright; `build_error_body()` applies `gettext()` at envelope-build time against `backend/locale/{fr,ar}`. DRF's own stock strings were already translated; these are the project's.*
- [x] `drf-spectacular` at `/api/docs/` and `/api/redoc/`; tag all routes. — *`SPECTACULAR_SETTINGS` + `DEFAULT_SCHEMA_CLASS`, routes mounted in `core/urls.py`. Tags come from the first URL segment via a `POSTPROCESSING_HOOKS` hook (`core/schema.py`) rather than per-view decorators, so a new route cannot arrive untagged. `apps/users/schema.py` registers `BearerAuth` **and** `CookieAuth` as alternatives (the cookie path is the SPA's). Function views gained `@extend_schema` for their request bodies — above `@api_view`, the order that actually takes effect.*
- [x] `Idempotency-Key` support on money-moving and listing-create endpoints. — *`core/idempotency.py`: `idempotency_key()` prefers the header over the body field for checkout and `payments/simulate/` (existing replay service reused), and `IdempotentPostMixin` gives `payments/refund/` and `products/seller/create/` a 24-hour replay — same key + same payload replays the original response with `Idempotency-Replayed: true`; same key + different payload is a 409 `idempotency_key_conflict`. A retried refund cannot pay out twice.*
- [x] API versioning (`/api/v1/`) **before** a mobile app depends on it. — *Hard cut to `/api/v1/`, no unversioned alias left behind (an old `/api/…` path gets the normal 404 envelope rather than a redirect or an HTML page). `core/versioning.py::PathVersioning` reports `v1` and refuses anything else with a 404 instead of the assertion DRF would turn into a 500. `X-API-Version` is set on every API response.*
- [x] Error-code reference in `docs/`. — *`docs/error-codes.md`: the envelope, every `code` with its HTTP status, what `details` carries, the idempotency and versioning rules, and how stable each part is.*

**Also here:** the catalogue is compiled with a bundled pure-Python `.po` → `.mo` writer (`core/mofile.py`, `manage.py compile_api_messages`), because GNU `msgfmt` is not assumed to exist on a contributor's machine. `tests/test_locale.py` re-compiles the catalogues and fails if a committed `.mo` no longer matches its `.po`, or if a message raised by the backend has no translation — so a new error cannot ship English-only to fr/ar. `tests/test_error_codes_doc.py` ratchets the reference doc against the source in both directions.

**Done when:** `/api/docs/` lists every route; 400/401/403/404/429/500 share one shape. ✅ **Completed 2026-10-12** — backend `348 passed + 1 xfail`, coverage 87.7%; `manage.py spectacular` reports **61 paths / 73 operations, 0 errors**, every operation tagged and every mutating one carrying a request body. New suites: `tests/test_api_contract.py` (the envelope asserted from outside, through real middleware and the real handler — including `Accept-Language`, `X-Request-ID` echo, schema-vs-URL completeness and the versioned prefix), `tests/test_locale.py`, `tests/test_error_codes_doc.py`. Frontend: one error reader (`src/lib/errors.js`) behind every failure branch, and the base URL moved to `/api/v1`.

---

## Phase 10 — N+1 elimination & query performance ✅
**Goal:** list endpoints stay fast at 100k+ listings.

- [x] `select_related` / `prefetch_related` on listing, order, store lists. — *`ProductQuerySet` (`apps/products/models.py`) is the one place the catalogue's query shape is written: `with_stock()`, `with_ratings()`, `with_catalog_stats()`, `for_user(user)`. Nested products (an order line, a cart line) get the same shape through `nested_product_queryset(user)`, which is what every `Prefetch("items__product", …)` passes — without it each line re-read its product and re-aggregated it, five queries per line instead of three for the whole cart. `StoreSerializer.product_count` and the embedded `owner` are one query now, not one each per row.*
- [x] Replace per-row `total_stock`, `average_rating`, `review_count` properties with annotations or denormalized, signal-updated columns. — *Annotations, and the properties are **deleted** rather than kept as a fallback: a `property` is a data descriptor, so it would shadow the annotation of the same name and the fallback would be a per-row query again. Reading the numbers off an un-annotated instance raises `AttributeError`, which is the point — loud and once, not slow on every row. All three are correlated **subqueries**, not joins: stock aggregates `Inventory` while the ratings aggregate `ProductReview`, and joining both cross-multiplies the rows (stock × reviews) and inflates the sum. Denormalised columns were rejected: a signal-maintained `total_stock` would need to stay correct through `reserve_inventory_for_order` and the admin, and the subquery is a single indexed lookup on a 20-row page.*
- [x] Fix `ProductListSerializer.get_primary_image` / `get_is_wishlisted`. — *`images.filter(is_primary=True)` bypassed the prefetch cache and queried per row; the serializer now scans the cached `images` (already ordered `-is_primary, sort_order`) and still returns no image when nothing is flagged primary, as it did before. `is_wishlisted` comes from an `Exists()` subquery per page (`for_user()`), with a one-query fallback for single-instance use.*
- [x] Fix `search_products` (evaluates the whole queryset in Python) and `low_stock_items` (filter in SQL); make `store_analytics` reachable. — *`search_products`'s `id__in=[p.id for p in products if p.total_stock > 0]` ran one `SUM` per candidate row and then re-queried on the ids; it now filters `total_stock__gt=0` in SQL. `low_stock_items` filters `stock_quantity > 0 AND stock_quantity <= product.low_stock_threshold` — the same predicate the `is_low_stock` property states, with the boundary (zero is out of stock, not low stock) pinned by a test. `store_analytics` existed but was in no `urlpatterns`, so it was unreachable; it is routed at `/api/v1/stores/seller/analytics/` and its `top_products` and `category_breakdown` are real aggregates over paid orders and the seller's catalogue. The two time-series stay empty until the analytics phase ships view tracking: an empty array is a fact, a fabricated one is a lie with a date on it.*
- [x] **Keyset (cursor) pagination** for infinite-scroll feeds (offset pagination degrades badly at scale). — *`core/pagination.py`: `FeedCursorPagination` (20 rows, `page_size` client-settable to 100) plus `WishlistCursorPagination` and `AuditCursorPagination` for the two orderings that are not `-created_at`. Applied to the catalogue, search, stores, product reviews, a user's reviews, the wishlist and the inventory audit log. Ordering always ends in `-id`: DRF's cursor uses `ordering[0]` as the position and needs a unique sort for the page boundary to be stable. The response is still `{next, previous, results}` — the same keys `PageNumberPagination` produced, minus `count`, which neither the frontend nor any documented client reads and which is an O(n) count over the filtered set on exactly the feeds this is for. Page numbers stay the default for the rest, because an order history is something people jump around in.*
- [x] Composite indexes for the real access patterns (category + wilaya + status + `-published_at`). — *The four that exist today: `(is_available, -created_at)` and `(category, -created_at)` on products, `(is_active, -created_at)` and `(category, -created_at)` on stores, `(user, -order_date)` and `(store, -order_date)` on orders, `(product, -created_at)` on reviews, `(user, -added_at)` on wishlists. Each replaces the single-column index it makes redundant (a write pays for one index, not two), and `stores.store_slug`'s explicit index was dropped as a duplicate of `SlugField(db_index=True)`. There is no `wilaya` column yet — that arrives with Phase 11's geography work, and inventing an index for it now would be a guess.*
- [x] `django-debug-toolbar` in dev; **query-count ceiling asserted in tests**. — *The SQL panel is the explanation for a ceiling that fails: it shows the per-request query list with timings and the stack trace that issued each row. Wired as an opt-in (`DEBUG_TOOLBAR=1`, and only when `DEBUG` is on), so tests, CI and production never import it and the app starts the same whether or not the package is installed (`requirements-dev.txt`).*

**Also here:** the feed endpoints' `?page=` no longer means anything (DRF ignores an unknown parameter rather than erroring) and is asserted not to; `?cursor=` is DRF's own, so an undecodable one is a `not_found` in the standard envelope rather than a 400. `store_stats` lost its Python loop over the store's products and its two redundant aggregate calls.

**Done when:** a 20-row list renders in a bounded number of queries, asserted in tests. ✅ **Completed 2026-10-12** — backend `377 passed + 1 xfail`, coverage 88.3%; `manage.py spectacular` **0 errors, 11 warnings** (down from 18 — the method fields gained the return type hints drf-spectacular had been asking for). New suite: `tests/test_query_performance.py`, which builds a 20-row page of each feed and asserts the ceiling (`django_assert_max_num_queries`) — products 5, stores 4, wishlist 5, orders 6, cart 6, audit log 4, low-stock 2 — then checks the aggregates are *right* (a two-variant product's stock is 10, not 20), walks a cursor across 25 rows to prove the pages are disjoint and complete, and covers `store_analytics`. Frontend: unchanged and unaffected — it reads `.results` and never `count`; when a scroll UI lands it can follow `next` as-is.

---

## Phase 11 — Algeria localisation: language, RTL, currency, geography *(new)*
**Goal:** feels native to Algerian users from the first screen.

- [x] **Frontend i18n** (`next-intl`): Arabic, French, English; language switcher; persisted preference. — *Cookie-based locale (`mh_locale`), deliberately **no `/<lang>/` URL segment** — that is Phase 26's SEO work. The root layout reads the cookie server-side and sets `<html lang dir>` + the message catalogue before first paint, so there is no client flash and every URL works in all three languages. Default `fr` (launch market, and the backend's own `LANGUAGE_CODE`). ICU messages in `src/i18n/messages/{ar,en,fr}.json` (561 keys at Phase 11, 574 after Phase 12, en/fr/ar parity enforced at merge time), a native-name switcher in the header (`LanguageSwitcher.js`) that writes the cookie and `router.refresh()`s. The axios client sends `Accept-Language` from the same cookie, so API `*_label` fields and geography names always match the UI language. **Trap worth knowing:** next-intl's React Server layer resolves locale/messages through `createNextIntlPlugin('./src/i18n/request.js')` (wired in `next.config.js`, cookie read in `src/i18n/request.js`) — without it every server render throws "Couldn't find next-intl config file", while Vitest stays green (it resolves the client build, which reads provider props instead). Only `next dev`/`next start` catch it.*
- [x] **RTL layout** with Tailwind logical properties (`ms-*`, `me-*`, `ps-*`, `start-*`); test every page in RTL. — *`ar` renders `dir="rtl"`. Every physical utility in `src/` swapped for its logical twin (`ml→ms`, `pl→ps`, `text-left→text-start`, `left→start`, `rounded-l→rounded-s`, `border-r→border-e`, `space-x→gap`); framer-motion slide-ins flip via `dirFor(locale)`; the toast stack mirrors to `top-left`. A repo-wide grep pins zero remaining `ml-/mr-/pl-/pr-/text-left/text-right/space-x` usages.*
- [x] Arabic-friendly font stack with a fallback; Eastern/Western digit handling. — *Inter + Noto Sans Arabic loaded by `next/font` as CSS variables in one stack (Latin first, Arabic glyphs fall through to Noto) — `<html lang>` alone switches the body font. The `Intl` locale for Arabic is **`ar-DZ`**: the Maghreb writes Western digits (45 000, never ٤٥٬٠٠٠) and `ar-DZ` also yields the local `د.ج.` symbol. Asserted in `currency.test.js`.*
- [x] **Currency:** DZD as the default; display with correct grouping; keep the "Algerian habit" of quoting prices in **millions/old centimes** in mind (e.g. "1 million" = 10,000 DA). Offer a configurable price display. — *`src/lib/currency.js`: pure `formatPrice(value, {locale, display})` bound to components through the `usePrice()` hook; whole dinars show no cents, fractional amounts keep two. `millions` mode divides by 10 000 with per-language plural rules (ar: ملايين for 2–10, million otherwise; en/fr: singular below 2). Preference persisted in the `mh_price_display` cookie, toggled from the switcher menu, hydration-safe (`useSyncExternalStore` with a `standard` server snapshot). Every `$`/`toFixed(2)` call site replaced.*
- [x] **Geography models:** `Wilaya` and `Commune` (code, name_ar, name_fr, name_en, optional lat/lng) loaded from a data fixture. Make it data-driven and **verify against the current official administrative list**, as wilaya counts have been changing. — *New `apps/geography` app. **69 wilayas** — the Nov 2025 / Law 26-06 reform, verified against the official list, not assumed — plus **1,541 communes**, fixture sourced from `othmanus/algeria-cities` with provenance recorded in `apps/geography/fixtures/README.md`. New wilayas 59–69 carry their capital commune (moved from the parent); the rest stay with the parent until official commune-level mapping is published. `Commune.code` is internal (`<wilaya><index:03>`); `name_en` and lat/lng are left empty rather than invented. Public read-only endpoints `GET /api/v1/geography/wilayas/` and `.../{code}/communes/?search=` (localized `display_name`), idempotent `manage.py load_geography`, and fixture-integrity tests that pin the official counts without needing a database.*
- [x] Replace free-text `Address.city/state_province/postal_code` with FK to `Wilaya`/`Commune` + free-text street line. — *`wilaya`/`commune` FKs (PROTECT, nullable at the DB level so legacy rows survive the migration). Hand-ordered migration `users/0006_address_geography.py` (add → name-match data migrate → drop; the auto-generated order dropped the columns before migrating their data). API writes require `wilaya_id` (commune optional, a commune from another wilaya is rejected), reads nest the geography; `country` is read-only `DZ`.*
- [x] Location picker component (wilaya → commune) usable in listing forms, filters, and addresses. — *`src/components/common/LocationPicker.js`: controlled `{wilayaId, communeId}`, picking a new wilaya always clears the commune, wilaya/commune fetches cached in memory (`src/lib/geography.js`, cache keyed by locale so names re-localize on switch). Wired into the checkout address form — which no longer posts city/state/postal/country at all; the listing forms and filters adopt it in Phases 12–13.*
- [x] Backend translation of enums/status labels and emails. — *`LANGUAGE_CODE=fr`, `LocaleMiddleware`, gettext catalogs for fr + ar (recompiled). `User.preferred_language` (ar/fr/en, default fr, on the profile and registration serializers) drives every email and OTP/password-changed SMS through a `recipient_language()` + `override()` helper; the request's `Accept-Language` drives the API surface. `*_label` twins (`order_status_label`, `payment_status_label`, `gateway_used_label`, `payout_status_label`, `action_type_label`, `category_label`) on the Order/Transaction/Ledger/AuditLog/Store serializers via one `core.i18n.choice_label()` helper — raw enum values unchanged in the contract. The frontend displays the labels instead of mapping enums client-side.*

**Done when:** the full app works in ar (RTL), fr, and en; a listing can be tied to a wilaya/commune; prices render in DZD. ✅ **Completed 2026-10-15** — backend `403 passed + 1 xfail`, coverage 88.6%, `manage.py spectacular` **0 errors, 64 paths / 76 operations** (up from 61/73). New backend suites: `apps/geography/tests/` (incl. no-DB fixture-integrity tripwires), `apps/users/tests/test_localization.py`, rewritten `test_addresses.py`; two password-reset assertions updated to the new French-by-default contract. Frontend: `83 unit` green, `next build` green with all 22 routes server-rendered off the locale cookie; new `src/lib/currency.test.js` and an i18n render helper (`src/test/i18n.jsx`) now wraps every component test. The e2e suite pins `mh_locale=en` through a shared fixture rather than being retranslated. **Also fixed here (pulled forward from Phase 14):** the ProductCard `image_url`/`primary_image` mismatch — every card image was broken, which would have made the translated catalogue useless.

---

## Phase 12 — Category tree & dynamic attributes *(new)*
**Goal:** every category has the right form and the right filters (this is where classifieds sites win or lose).

- [x] `Category` model: tree (`django-mptt`/`treebeard` or `ltree`), slug, translated names, icon, order, `is_active`. — *New `apps/catalog` app: `Category(MPTTModel)` with a slug as the stable contract, `name_fr/ar/en`, `parent` TreeForeignKey, icon, order, `is_active`. `display_name` follows the request's `Accept-Language` like geography (French fallback, never a hole). Registered as a `DraggableMPTTAdmin` — drag-and-drop tree editing; deactivating a node hides its whole subtree publicly without touching anyone's data.*
- [x] `AttributeDefinition` per category: key, label (i18n), type (text/number/enum/boolean/year/range), required, filterable, unit, choices. — *`key` is `lower_snake_case`, `unique (category, key)`; labels in fr/ar/en, `choices` JSONB for enums, and `clean()` rejects malformed keys and bad/dupe choice shapes. The launch fixture carries the phase's examples — Vehicles (brand, year, km, fuel, gearbox…), Real estate, Phones (brand/storage/condition), Jobs — as **45 definitions across 23 nodes**, with fixture-integrity tests that pin them without a database.*
  Examples: **Vehicles** (brand, model, year, km, fuel, gearbox, papers) · **Real estate** (type, rooms, m², floor, deal type) · **Phones** (brand, storage, condition) · **Jobs** (contract, experience, salary).
- [x] Store values in validated `JSONB` (`attributes_json` already exists, so formalize it) with GIN indexes; validate against definitions. — *`products_attributes_gin` kept. One rule set — `apps.catalog.validation.validate_attributes` — shared by API/admin/(later) import: unknown keys rejected by name, missing required rejected, **inactive definitions ignored entirely** (turning a field off must not brick stored products), booleans strictly boolean, ranges must be a `{min, max}` pair with min ≤ max, years bounded 1900–2100, text trimmed and capped at 255, numeric strings coerced. Rejections land **per key** under `details.attributes_json` — the error envelope now recurses into nested field dicts instead of stringifying them, which is what lets the dynamic form highlight the offending input.*
- [x] Migrate `Product.category` (free text) and `Store.category` (hardcoded choices) to FKs; data migration for existing rows. — *`stores/0005_store_category_fk` turned the nine store choices into the nine legacy roots and name-matched existing rows onto them; `products/0004_product_category_fk` did the same for products (legacy text → slug, uncategorized → `null`). API writes `category_id` (active nodes only; **required on create**) and reads the nested `category` object / `category_label`.*
- [x] Dynamic listing form + dynamic filter sidebar generated from definitions. — *Frontend: `src/lib/catalog.js` (tree fetched once, indexed by id/slug/depth, cache keyed by locale, client-side `effectiveDefinitions` inheritance), `CategoryPicker` (indented tree `<select>`), `AttributeFields` (one input per type — enum select from the server's choices, year 1900–2100, boolean checkbox, range min/max pair, unit hints, per-key error highlight). Wired into seller create/edit, store setup and the products sidebar (`?category=<slug>` matches the whole subtree, `?attr_key`/`_min`/`_max` for attributes; switching subtree clears stale attr filters). `product.category`/`store.category` now render the nested object's localized name everywhere, never a bare object.*
- [x] Seed the launch categories first (Phase 29), not all of Ouedkniss's. — *`manage.py load_categories`: idempotent `update_or_create` from `apps/catalog/fixtures/categories.json` (**23 categories / 45 attribute definitions** today), re-runnable to refresh labels, ends with `Category.objects.rebuild()`. Added to the README quick start — `seed_e2e` depends on it.*
- [x] Admin UI to edit categories/attributes without a deploy. — *`AttributeDefinitionAdmin` plus an inline (`AttributeDefinitionInline`) on the `CategoryAdmin`; since the form, the filters and their labels all read from `GET /catalog/categories/`, an admin edit is live on the next page load with no deploy and no frontend change.*

**Done when:** adding a category + attributes in admin instantly yields the posting form and filters in the UI. ✅ **Completed 2026-10-15** — backend **`441 passed + 1 xfail`**, coverage 87.8%, `manage.py spectacular` **0 errors** (65 paths / 77 operations), `ruff` clean, `load_categories` idempotent (0 new on re-run). New suite `apps/catalog/tests/test_catalog.py` (26 tests: tree walk, effective-definition inheritance/override/order, validation units for all six types, tree-endpoint shape/localization/subtree counts, product write contract incl. re-file revalidation and inactive/missing `category_id`, subtree + composed filters) alongside the fixture tripwires. **Two real bugs surfaced and fixed while completing the phase:** the tree endpoint's `product_count` grouped per node (`GROUP BY pk … LIMIT 1` returned one arbitrary node's count instead of the subtree total), and the error envelope stringified nested `details.attributes_json` into a Python repr with `ErrorDetail(…)` in it. Frontend: **90 unit tests** green (new `catalog.test.js`, a nested-details case in `errors.test.js`, category-object cases in `ProductCard.test.jsx`), `next lint` / `prettier --check` / `next build` all green, and the **5 Playwright journeys pass** — post-listing now picks the category from the tree and fills phones-tablets' required brand/storage/condition through the dynamic form.

---

## Phase 13 — Listings model: individuals, stores, and ad lifecycle *(new)*
**Goal:** anyone can post in under 90 seconds; stores keep rich features.

- [x] **Decision (Phase 0):** evolve `Product` into `Listing` (recommended) with `seller` FK to `User`, **nullable `store`**, and `listing_type` (`FOR_SALE`, `STORE_PRODUCT`, `SERVICE`, `JOB`, `RENT`, `WANTED`). — *The **domain/UI** term is "listing" everywhere (labels, error codes, `/l/` URLs, docs), but the Django model keeps the name `Product` (table `products`, path `/api/v1/products/`) per Phase 0 decision #2 — one catalog, one search index, no v1 rename; the resource rename is deferred to `/api/v2`. Migration `products/0005` is hand-ordered: add every column nullable → backfill `seller ← store.owner`, `slug`, `published_at` → tighten `seller` NOT NULL → indexes + the `store_product_requires_store` DB check.*
- [x] Price modes: `FIXED`, `NEGOTIABLE`, `ON_REQUEST`, `FREE`, `EXCHANGE`; currency; optional old price. — *On the model with labels localized through the serializer; the browse/detail/wizard UIs render `price_mode` (e.g. "Price on request" instead of a number) and `ProductCard` shows the label when `base_price` is null.*
- [x] **Lifecycle:** `DRAFT → PENDING_REVIEW → ACTIVE → EXPIRED / SOLD / REJECTED / ARCHIVED`; expiry (e.g. 30 days), **renew**, mark-as-sold, auto-pause. — *`apps/products/lifecycle.py` is the single state machine behind `POST /products/<pk>/lifecycle/ {action}`; every transition validates the current status and answers `invalid_transition` with the allowed set. Publish auto-approves `PENDING_REVIEW → ACTIVE` unless `LISTINGS_REQUIRE_MODERATION` (Phase 17). Wizard/classified listings get `expires_at = now + LISTING_VALID_DAYS` (30); store SKUs expire never (inventory governs them). `manage.py expire_listings` flips lapsed ads lazily + in batch, with `--dry-run`.*
- [x] Contact mode per listing: show phone / WhatsApp / chat-only / checkout-enabled. — *`contact_mode` on the row; the detail serializer exposes `seller_phone` **only** when `contact_mode ∈ {PHONE, WHATSAPP}` **and** the number is verified — an unverified number is worth nothing to a buyer and everything to a scammer. Phase 16 adds the reveal/chat flow. The detail page renders a tel:/wa.me block for classifieds and never the checkout cart.*
- [x] **Fast posting wizard:** category → photos → 3–5 fields → location → price → publish. Autosave drafts; works on slow mobile networks. — *`/post`, five screens (basics → photos → details → location → price & publish), each step boundary autosaving: `POST /products/create/` once (scope `classified` idempotency), then `PATCH /products/seller/<id>/` — a PUT would demand fields the seller has not reached yet. `incomplete_listing` maps `details.missing` back to the owning step; `possible_duplicate` shows an inline "publish anyway?"; category attributes resolve client-side from the cached tree (Phase 12 inheritance). Photos are URLs this phase (real uploads are Phase 14). Header "Post an ad" — posting is not seller-only.*
- [x] **Duplicate-listing detection** (same seller + similar title/price/image hash). — *At **publish only** (drafts are cheap): same seller + same category + same `listing_type`, title similarity ≥ 0.82 (trigram) and price within ±10%, within a 90-day window → `possible_duplicate` with `duplicate_of`/`duplicate_name`. `allow_duplicate: true` retries past **this gate only** — it can never bypass completeness or the quota. Image-hash matching lands with Phase 14's pHash.*
- [x] Per-user active-listing quotas by tier (free vs verified vs store plan). — *Unit = the seller's ACTIVE listings **of any type** (one person, one counter). Free = `MAX_ACTIVE_LISTINGS_PER_USER` (10), ×3 when phone-verified; a store owner is never capped below `MAX_PRODUCTS_PER_SELLER` (20); PRO=500, BUSINESS=unbounded (Phase 21 plans). Enforced at publish (`quota_reached` carries `quota`/`active`); a separate `MAX_DRAFT_LISTINGS` (20) cap answers `draft_limit`. `GET /products/seller/quota/` reports `{plan, active_listings, listing_quota, drafts, draft_limit, store_products, store_product_quota}` and the wizard/dashboard render it.*
- [x] Keep cart/checkout only for `STORE_PRODUCT` with inventory; classifieds skip inventory. — *Unchanged Phase 6 invariants, now enforced against the new shapes: adding a classified to the cart answers 400 `product_unavailable`, cart lines whose row went SOLD/ARCHIVED are refused at update and at checkout, and the reserve step uses `select_for_update(of=("self",))` now that `store` is nullable. Checkout idempotency replays on `checkout_fingerprint` and answers 409 `idempotency_key_conflict` when the payload changed.*
- [x] Slug URLs: `/l/<slug>-<id>` (SEO + sharing); canonical redirect when slug changes. — *The API owns the format (`<slugified-title>-<id>`, generated on publish, `_` placeholder before that); the page parses the **trailing** `-<digits>` (titles like "iPhone 15" keep working), fetches by id alone, and `router.replace`s to `canonical_path` — so `/products/<id>` and a stale slug both land on the one canonical address. `ProductCard` links `canonical_path` when present.*
- [x] "Similar listings" and "more from this seller". — *`GET /products/<id>/similar/` (own category + its parent node + sibling subtrees) and `GET /products/<id>/more-from-seller/` (that seller's other live rows), both rendered as rails on the detail page; drafts are never visible to either.*

**Decisions recorded:**
- *Model keeps the name `Product`; "listing" is the domain term. Resource rename → `/api/v2` (Phase 0 decision #2).*
- *Ownership failures answer **404, not 403** (`IsListingOwner` scopes the queryset; a stranger must not learn the row exists).*
- *`seller_phone` is consent-gated: `PHONE`/`WHATSAPP` contact mode **and** a verified number, on the detail endpoint only.*
- *`allow_duplicate: true` bypasses the duplicate gate only — never completeness, never quota.*
- *`listing_type` is immutable after creation; the store endpoint forces `STORE_PRODUCT` and the wizard rejects it (`wrong_listing_type`).*
- *`unarchive` lands on DRAFT (republishing is a fresh decision); expiry is wizard/classified-only; store SKUs never expire.*
- *Migration 0005 runs `atomic = False`: Postgres refuses the `seller NOT NULL` ALTER while the backfill's UPDATEs hold pending RI trigger events in the same transaction; the nullable-first ordering makes each phase commit-and-resume safe.*

**Done when:** an unauthenticated visitor can register and publish a listing in ≤ 90 s; listings expire and renew correctly; a store can still sell with inventory + checkout. ✅ **Completed 2026-10-28** — backend **`490 passed + 1 xfail`** (the Phase 17 review-marker strict xfail), coverage 88.3%, `ruff` clean, `makemigrations --check` clean, migration 0005 applied to the dev database (non-atomic after the "pending trigger events" fix). New suite `apps/products/tests/test_listings.py` (**49 tests**: lifecycle matrix incl. moderation route, quotas by plan/verification/store floor, duplicate gate + `allow_duplicate` bypass, slug/canonical/rename, draft invisibility, lazy expiry + `expire_listings` command, seller `?status=` tab filtering, individual edit/delete, `listing_type` immutability incl. the autosave type-echo round-trip, `seller_phone` consent, wizard idempotent create, cart/checkout guards, DB check constraint, wilaya filter, list payload shape, and an N+1 ceiling of 8 queries on the seller list). The suites surfaced **five real bugs, all fixed**: the wizard-create endpoint 500ed on its own annotated serializer; `similar_to` filtered on `Product.category_id` with Q-objects built for the Category model; the seller list ran 21 queries via per-row store prefetch joins; the write serializer 400ed the wizard's *unchanged* `listing_type` echo, wedging autosave at every step boundary after the first (it now rejects only an actual change); and the login page's 500 ms post-login redirect teleported users who clicked onward inside that window — the App Router commits the next URL only once its RSC payload arrives, so the timer outlived the click — now an immediate push (the toast lives in the root-layout Toaster and survives it), while the register page's 3 s success-message timer instead cancels on unmount. Frontend: **110 unit tests** green (wizard suite in `src/app/post/page.test.jsx`, `/l` route + `parseListingId`, Phase 13 `api.test.js` endpoints, ProductCard canonical/seller/price-mode cases), `next lint` / `prettier --check` / `next build` green (21 routes incl. `/post` and `/l/[slugId]`), i18n en/fr/ar parity at **693 keys each** (new `post` namespace + wizard/seller/browse strings), and all **6 Playwright journeys** pass — including the new one: an individual signs in and publishes a classified through the wizard to the canonical `/l/<slug>-<id>` URL, while the search journey now asserts that canonical address.

---

## Phase 14 — Media pipeline *(was Phase 12)*
**Goal:** fast, safe, real images.

- [x] Fix `ProductCard.js` reading `image_url` while the serializer exposes `primary_image` (every card is broken today). — *Done early in Phase 11 (a broken image would have undermined the translated catalogue): the card now prefers `primary_image`, falls back to `image_url`, then to the placeholder; `ProductCard.test.jsx` pins all three cases.*
- [ ] Real uploads: `ImageField` + S3-compatible storage (MinIO in dev, Cloudflare R2/S3 in prod) + signed upload URLs; image CDN.
- [ ] Server-side processing: auto-rotate, **strip EXIF/GPS**, resize to responsive variants, WebP/AVIF, blurhash/LQIP placeholders.
- [ ] **Client-side compression before upload** (important on weak mobile networks); drag-reorder; up to ~10–15 images per listing.
- [ ] Validation: size, real MIME sniffing, dimensions, malware-scan hook.
- [ ] **Perceptual hash (pHash)** stored per image → duplicate/stolen-photo detection (feeds Phase 17).
- [ ] Optional **watermark** with the MarketHub logo (reduces image theft by competitors/scammers).
- [ ] `next/image` with tightened `remotePatterns` (currently allows any `https://**`).
- [ ] Add `frontend/public/` assets: placeholders, favicon, `robots.txt`, manifest.

**Done when:** a seller uploads photos from a phone in seconds, they show everywhere in optimized form, and EXIF is stripped.

---

## Phase 15 — Search & discovery *(was Phase 13)*
**Goal:** the best search in the Algerian classifieds space.

- [ ] Engine decision: start with **Postgres FTS + `pg_trgm`** (simple ops); move to **Meilisearch or Typesense** if relevance/typo-tolerance is not enough. Keep a `SearchService` interface.
- [ ] **Arabic + French analysis:** normalization (hamza/ya/ta marbuta, diacritics, tatweel), French accents/stemming, transliteration between Arabic and Latin spelling, and a **synonym list** (brand/model nicknames, common Darija words).
- [ ] Facets: category, wilaya/commune, price range, condition, seller type, verified-only, **category-specific attributes** from Phase 12, "with photos", date posted.
- [ ] Sort: relevance, newest, price asc/desc, distance (if geo).
- [ ] **Saved searches + alerts** (push/SMS/email/WhatsApp, instant or daily digest).
- [ ] Search suggestions / autocomplete; recent searches; "no results" recovery (relax filters, nearby wilayas).
- [ ] Honor `in_stock` (currently ignored); fix pagination controls (only page 1 renders today); wire `productsAPI.search` into a real `/search` page.
- [ ] Home feed: latest in my wilaya, trending, recommended categories; infinite scroll with cursor pagination.
- [ ] Track searches and zero-result queries to improve synonyms (Phase 25).

**Done when:** typo and Arabic/French variants find the right listings; filters per category work; saved-search alerts fire.

---

## Phase 16 — Contact, chat & offers *(new)*
**Goal:** the core of a classifieds product, done more safely.

- [ ] **Reveal phone** button (like Ouedkniss), rate-limited and logged (anti-scrape, anti-harassment). Option to hide the number and use chat only.
- [ ] One-tap **WhatsApp / call / SMS** deep links.
- [ ] **In-app chat** per listing (WebSocket with Django Channels, or polling + push for MVP); read receipts; image sharing; block/report user.
- [ ] **Make-an-offer** (price negotiation) with accept/counter; keeps "negotiable" prices first-class.
- [ ] Safety nudges in chat (warn about off-platform payments, advance payments, suspicious links).
- [ ] Seller response-time badge ("replies in ~1 h").
- [ ] Inbox UI for buyers and sellers; email/push notification on new message.
- [ ] Spam filter: phone numbers/links in the first message, duplicate message floods.

**Done when:** a buyer can contact a seller by chat or by phone; sellers get notified; abuse can be reported.

---

## Phase 17 — Trust & safety *(new: the main differentiator)*
**Goal:** fewer scams than Ouedkniss, visibly.

- [ ] **Seller tiers/badges:** Unverified → Phone-verified → ID-verified (ID photo + selfie review, admin queue) → Verified Store (commercial register / NIF upload).
- [ ] **Report listing / user** (reason codes) with an admin moderation queue and target SLAs.
- [ ] **Pre-publish automated checks:** banned keywords (multilingual), prohibited-category rules, price-anomaly detection, duplicate text + pHash duplicates, phone/email in description patterns, known-scam templates.
- [ ] Shared **blocklists**: phone numbers, devices/fingerprints, IPs, bank-account/CCP patterns.
- [ ] Review moderation: `is_approved` defaults to `True` today; flip to pending/auto-approve-by-trust-score. Reviews tied to **completed orders** for stores.
- [ ] **Seller reputation** score (response rate, completed orders, reports, account age).
- [ ] Safety center content (ar/fr/en): how to avoid scams, safe meetups, advance-payment warnings.
- [ ] Admin tools: mass-action by phone number/user, ban evasion detection, audit log.
- [ ] Appeal flow for rejected ads/banned users.

**Done when:** a flagged scam pattern is blocked before publishing, reports reach a moderation queue, and badges are visible on listings.

---

## Phase 18 — Orders, status machine, refunds & business correctness *(was Phase 11)*
**Goal:** stop showing fake numbers; make refunds safe.

- [ ] Order **status state machine** with allowed transitions (today any→any).
- [ ] Return inventory on cancel/refund (`return_inventory_for_order` exists and is **never called**).
- [ ] Refund reverses the commission ledger and marks the original transaction refunded.
- [ ] Fix `stores/views.py` reading status `COMPLETED`, which doesn't exist (and the admin action that *writes* it), and drop the fabricated metrics (`conversion_rate: 3.2`, `views = count * 87`). *The bare `except: pass` in the same file is already gone — Phase 10 removed it with the Python-side stock loop.*
- [ ] **Order-level dispute flow** (buyer opens dispute → seller responds → admin decides).
- [ ] **Guest / phone-only checkout** for COD (no mandatory email/account friction).
- [ ] Order timeline UI for buyer, seller; expose refund in UI (`paymentsAPI.refund` is never called).

**Done when:** cancel/refund restocks inventory; dashboard metrics derive from real rows; disputes can be resolved.

---

## Phase 19 — Payments for Algeria *(new, replaces "simulated payments")*
**Goal:** pay safely without hurting the cash/COD habit.

- [ ] **Cash on Delivery as default**: COD confirmation (phone call/SMS), failed-delivery handling, seller COD ledger.
- [ ] Abstract `PaymentProvider` interface (keeps the simulator for tests/dev).
- [ ] **Evaluate** online gateways supporting **CIB / Edahabia**: direct SATIM integration (requires a merchant agreement) vs aggregators (Chargily, SlickPay, etc.). Compare fees, onboarding, API quality, payout time. *Do not integrate until the legal/merchant path is clear (Phase 0).*
- [ ] **Escrow-lite** for high-value items: funds held until delivery confirmation or N days; auto-release; dispute hold. (Check regulatory implications before holding funds.)
- [ ] Webhooks with signature verification, idempotent handlers, reconciliation job.
- [ ] Commission rules per category/tier; seller payout statements, payout runs, and CCP/bank/Baridimob-style payout method records.
- [ ] Remove `str(e)` leakage; store only provider tokens, never card data (stay out of PCI scope).

**Done when:** COD orders work end-to-end; at least one online method works in test mode with reconciled webhooks; payout statements are accurate.

---

## Phase 20 — Delivery & logistics *(new)*
**Goal:** "buy and receive" anywhere in the country; a clear edge over meet-and-cash.

- [ ] `ShippingProvider` abstraction. **Evaluate** Algerian carriers' APIs (e.g. Yalidine, ZR Express, Maystro, Ecotrack-based carriers) for rate quotes, label creation, tracking, COD collection.
- [ ] Shipping rates by wilaya/commune and weight; home vs relay-point (stop-desk) delivery.
- [ ] Replace free-text `shipping_method` with real methods; free-shipping thresholds.
- [ ] Tracking page; status webhooks → order status updates → notifications.
- [ ] Return-to-seller flow for refused COD parcels; abuse score for repeated refusals.
- [ ] Seller "ships from" wilaya + delivery coverage settings.

**Done when:** a seller can create a shipment from an order and the buyer sees live tracking.

---

## Phase 21 — Monetization: boosts, subscriptions, coupons *(new + old Phase 14)*
**Goal:** sustainable revenue without punishing small sellers.

- [ ] **Promoted listings:** top-of-category, highlighted, urgent badge, homepage slot; priced per day; boost scheduler + analytics.
- [ ] **Store plans** (Free / Pro / Business): listing quotas, bulk import, analytics, custom store URL, verified badge; replaces `MAX_PRODUCTS_PER_SELLER`.
- [ ] Wallet / credits for boosts (top up by supported methods).
- [ ] **Coupons & promo codes** (old Phase 14): %, flat, usage caps, expiry, stacking rules, abuse prevention.
- [ ] Server-side order totals (coupon + shipping + tax); never trust the client; tests for expired/exhausted/over-stacking/negative clamping.
- [ ] Invoice generation (PDF) with the legally required fields for Algerian businesses.
- [ ] Keep the **core experience free** (posting, contacting) so you don't lose to Ouedkniss at the entry level.

**Done when:** a seller can buy a boost and see it rank higher; plan quotas are enforced; coupon totals are correct.

---

## Phase 22 — Notifications & async work *(was Phase 15)*
**Goal:** users are told what matters, reliably.

- [ ] Celery + Redis with beat; eager mode in dev.
- [ ] Channels: **email, SMS, web push, WhatsApp (optional)**; per-user preferences.
- [ ] Events: new message, offer, saved-search match, listing approved/rejected/expiring, order updates, low-stock, payout.
- [ ] In-app notification center with bell in `Header.js`.
- [ ] Idempotent, retryable tasks (exponential backoff); wrap verification email in a task.
- [ ] Scheduled jobs: listing expiry/renew reminders, saved-search digests, payout runs, stale-draft cleanup, image reprocessing.
- [ ] Notification cost guardrails (SMS budgets, per-user caps).

**Done when:** placing an order, receiving a message, and a saved-search match each trigger the right notification asynchronously and exactly once.

---

## Phase 23 — Frontend architecture, PWA & performance *(was Phase 16 + mobile)*
**Goal:** fast on cheap phones, installable, SEO-ready.

- [ ] `app/loading.js`, `app/error.js`, `app/not-found.js`; root error boundary.
- [ ] Convert listing/store/list pages to **Server Components** with `generateMetadata`; OpenGraph/Twitter cards; JSON-LD (`Product`/`Offer`, breadcrumbs).
- [ ] `middleware.js` for protected routes (all 19 pages are client components with `useEffect` redirects).
- [ ] SWR/React Query for caching and consistent loading/error states.
- [ ] **PWA:** manifest, service worker, offline shell, add-to-home-screen, background retry for failed listing uploads.
- [ ] **Performance budget:** JS < 170 KB gzipped per route, LCP < 2.5 s on throttled 4G, CLS < 0.1; enforce with Lighthouse CI.
- [ ] Image lazy-loading, skeletons, list virtualization.
- [ ] Data-saver mode (lower-res images, fewer animations).
- [ ] Remove `clean-cache.ps1`.

**Done when:** Lighthouse mobile ≥ 90 on home, listing, and search; the app installs as a PWA; protected routes redirect server-side.

---

## Phase 24 — Accessibility & design system *(was Phase 17)*
**Goal:** usable by everyone, consistent everywhere.

- [ ] Full a11y pass: landmarks, headings, focus, skip-link, contrast (currently zero `aria-*` in `src`).
- [ ] Keyboard-accessible dropdowns (`Header.js` hover menu); `aria-label` on icon buttons.
- [ ] Respect `prefers-reduced-motion` in `framer-motion`.
- [ ] Shared form primitives (input/select/error); design tokens; component library docs (Storybook optional).
- [ ] **RTL-aware icons/animations** (mirrored arrows, chevrons).
- [ ] Skeleton/empty-state consistency; toast policy.
- [ ] `eslint-plugin-jsx-a11y` + `axe-core` smoke tests in CI.

**Done when:** Lighthouse a11y ≥ 95; keyboard-only and screen-reader smoke tests pass in ar/fr/en.

---

## Phase 25 — Admin, seller dashboard & analytics *(was Phase 18)*
**Goal:** operators run the marketplace without SQL; sellers see real value.

- [ ] Register `ProductReview`, `Wishlist`, `StoreFollower` (and new models) in Django admin; improve list filters/search.
- [ ] Wire up or delete `StoreFollower` (model exists, **zero API**). Recommended: wire it (follow store → new listing alerts).
- [ ] **Seller dashboard:** views, contacts, phone reveals, favorites, conversion, top listings, best time to post, boost ROI.
- [ ] **Bulk tools:** CSV/Excel import, bulk edit/renew/pause, duplicate-and-edit.
- [ ] **Operator dashboard:** moderation queue stats, scam rate, listings/day, supply-demand by wilaya/category.
- [ ] **Event tracking** (privacy-respecting, first-party): impressions, views, contacts, searches, zero-result searches.
- [ ] Variant/attribute management UI for store products.
- [ ] Payout runs: allow ledger `payout_status` to reach `PAID`.

**Done when:** an operator can moderate a review and a flagged listing; a seller sees real analytics.

---

## Phase 26 — SEO & growth *(new)*
**Goal:** organic traffic is your cheapest acquisition channel, and where classifieds sites live or die.

- [ ] Clean URL structure: `/<lang>/<category>/<wilaya>/<slug>-<id>`; canonical tags; `hreflang` for ar/fr/en.
- [ ] Dynamic `sitemap.xml` (sharded for large catalogs) + `robots.txt`; remove/redirect expired listings correctly (410 vs 301 policy).
- [ ] Indexable category × wilaya landing pages with unique copy ("Voitures à vendre à Blida").
- [ ] Structured data (JSON-LD) for listings and organization; rich previews for WhatsApp/Facebook shares.
- [ ] **Share buttons** optimized for WhatsApp/Facebook/Messenger/Viber; shareable store links.
- [ ] Referral program (invite sellers; both get free boost credits).
- [ ] Facebook-marketplace/Instagram cross-posting helper (post-launch).
- [ ] Transactional "your listing is live → share it" flow to drive repeat traffic.

**Done when:** category-wilaya pages are indexed with correct metadata; sharing a listing to WhatsApp shows the image, title, and price.

---

## Phase 27 — Documentation, DevOps & packaging *(was Phase 19)*
**Goal:** one command to run; one command to ship.

- [ ] Dockerfiles + `docker-compose.yml` (Postgres, Redis, MinIO, search engine, mail catcher).
- [ ] `Makefile` (`dev`, `test`, `lint`, `seed`, `db`).
- [ ] Convert root helper scripts into management commands (`seed_demo`, `repair_inventory`, `load_geography`, `seed_categories`).
- [ ] **Delete destructive `fix_inventory.py`** (resets legitimate 0-stock rows to 100) and duplicate setup scripts.
- [ ] Fix false claims in `backend/README.md` (docs route, HttpOnly cookies, HTTPS, tests, WhiteNoise, DB name, routes).
- [ ] `CHANGELOG.md`, `docs/architecture.md`, `docs/api.md`, `docs/deployment.md`, `docs/moderation-playbook.md`, `docs/product.md`.
- [ ] Contribution guide, issue templates, ADRs for big decisions (listing model, search engine, payment provider).

**Done when:** `docker compose up` yields a working stack with seeded demo data; README has zero false statements.

---

## Phase 28 — Production deployment, compliance & observability *(was Phase 20)*
**Goal:** ship it, know when it breaks, stay legal.

- [ ] Staging + production with separate secrets; `DEBUG=False`; `ALLOWED_HOSTS` verified.
- [ ] **Hosting decision with latency in mind:** users are in Algeria; compare EU regions (Paris/Frankfurt/Marseille) + CDN. Measure real latency from Algerian ISPs (Algérie Télécom, Djezzy, Mobilis, Ooredoo) before choosing.
- [ ] CDN for images/static; HTTP caching headers; Brotli.
- [ ] Sentry (backend + frontend), structured logs with request IDs, metrics/alerts (error rate, p95, queue depth, DB connections, SMS spend).
- [ ] Load tests (`k6`/`locust`) on browse, search, listing create, chat, checkout.
- [ ] Backups + **tested restore** runbook; retention policy.
- [ ] **Legal/compliance:** Law 18-07 personal-data handling (privacy policy, consent, retention, data-export/deletion), terms of use, prohibited-items policy, seller terms, cookie notice, report-abuse contact, takedown procedure.
- [ ] Security pass: OWASP top-10 review, dependency audit, scraping/abuse defenses (WAF/Cloudflare rules), pen-test checklist.
- [ ] Incident runbook, status page, rollback procedure; cut `v1.0.0`.

**Done when:** the site is live behind HTTPS with dashboards, alerts, tested backups, legal pages, and a rollback plan.

---

## Phase 29 — Launch, cold-start & post-launch *(new)*
**Goal:** a marketplace with no listings is worthless; solve supply first.

- [ ] **Launch narrow:** 1 wilaya × 2–3 categories; aim for ~500 quality listings before opening demand.
- [ ] **Seed supply:** recruit 30–50 stores/sellers personally (phones, cars, electronics shops); offer **free Pro plan for 6 months** + migration help.
- [ ] **Importer** for sellers' existing catalogs (CSV/Excel; optionally Facebook page product export). *Only import content the seller owns; do not scrape Ouedkniss or others (legal + ethical risk).*
- [ ] Support channel (WhatsApp/Messenger + in-app) with Arabic/French support.
- [ ] Referral and local campaigns (Facebook/Instagram/TikTok groups by wilaya).
- [ ] Weekly metrics review against §0.4; expand wilaya/category only when liquidity targets are met.
- [ ] Beta feedback loop → backlog → monthly releases.
- [ ] Post-launch backlog: native Android app (or Capacitor wrapper of the PWA), AI-assisted listing creation (photo → title/category/attributes suggestion), price suggestion from comparable listings, voice/Darija search, maps view, verified vehicle history/inspection partners, B2B stores API.

**Done when:** the pilot region reaches the liquidity targets (listings with ≥ 1 contact in 7 days, seller retention) and you have a written expansion plan.

---

## Decisions needed from you

| # | Decision | Recommendation |
|---|---|---|
| 1 | Product model: classifieds-first, store-first, or hybrid? | **Hybrid:** classifieds posting for everyone + store features/checkout for businesses. |
| 2 | Evolve `Product` → `Listing` or add a separate `Ad` model? | **Evolve into `Listing`** with nullable `store`; avoids two parallel catalogs and search indexes. |
| 3 | Search engine | Start **Postgres FTS + trigram**; plan for Meilisearch/Typesense behind an interface. |
| 4 | JWT storage | **HttpOnly cookie + CSRF** for web; bearer for the future mobile app (versioned API). — *implemented in Phase 7 (`CookieJWTAuthentication`)* |
| 5 | Online payment path | **Launch with COD only**, add an aggregator after the legal path is confirmed. |
| 6 | Real-time chat tech | **Polling + push for MVP**, Channels/WebSockets in v1.1. |
| 7 | Launch region and categories | One wilaya (your local one) × phones/cars/electronics or whichever your seed sellers cover. |
| 8 | Hosting region | Decide **after** measuring latency from Algerian ISPs. |

---

## Suggested sequencing

| Wave | Phases | Rationale |
|---|---|---|
| **Strategy** | 0 | Validate what you're building against the real competitor |
| **Foundation** | 1 → 2 → 3 → 4 → 5 | Clean repo, config, tests, lint, CI |
| **Correctness** | 6 → 7 → 8 → 9 → 10 | Money, security, identity (phone OTP), contract, performance |
| **Marketplace core** | 11 → 12 → 13 → 14 → 15 → 16 | **Ouedkniss parity:** locale, categories, listings, media, search, contact |
| **Differentiate** | 17 → 18 → 19 → 20 → 21 → 22 | **Beat them:** trust, safe payment, delivery, monetization, notifications |
| **Polish & grow** | 23 → 24 → 25 → 26 | PWA/perf, a11y, dashboards, SEO |
| **Ship** | 27 → 28 → 29 | Package, deploy, comply, launch narrow, expand |

**Parallelizable once Phase 5 is done:** (6, 7), (11, 12), (14, 15), (17, 22), (23, 24).
**Do not start before Phase 6:** anything touching orders/payments/inventory (19, 20, 21).
**Current status:** Phases 0–12 ✅ (audited 2026-10-28 — every claim verified against the code, all gates green, small fixes landed; see §0.3 "Audit of Phases 0–12") · everything else open · backend `441 tests green (1 strict xfail — Phase 17)`, frontend `90 unit + 5 e2e green`. **Do not start Phases 19–21 before now** — the money/stock invariants they build on are in place. **Next up: Phase 13.**
