# MarketHub — Roadmap to Production-Ready

> **Baseline audit (2026-10-09)**
>
> | Check | Result |
> |---|---|
> | `python manage.py test` | **0 tests found** → `NO TESTS RAN` (exit 1) |
> | `npm run lint` | **Fails** — no `.eslintrc`, prompts for config, `eslint-config-next@16` vs `next@14` mismatch |
> | `python manage.py check` | Passes, 0 issues |
> | Migrations | In sync (`makemigrations --check` → no changes) |
> | Backend | 67 files / 4,078 LOC · 6 apps · 51 routes |
> | Frontend | 29 files / 5,258 LOC · 19 pages (all client components) |
> | Git | 0 commits · **235 of 313 tracked files are build artifacts / `__pycache__` / `.env`** |
> | CI / Docker / lint / test config | **None** |
>
> **Verified critical defects** (all confirmed by reading source):
> 1. `backend/apps/orders/views.py:203-206, 218-221` — `return Response(...)` *inside* `transaction.atomic()` → partial commits.
> 2. `backend/apps/users/serializers.py:11-13` — `is_seller` writable via profile `PUT` → privilege escalation.
> 3. `backend/.gitignore` is a single line (`/frontend/node_modules/`); `.env.local`, `.next/`, `staticfiles/`, `__pycache__/` are all staged.

---

## Phase 1 — Repository hygiene & reproducible baseline ✅
**Goal:** a clean, trustworthy git history and a project anyone can clone and run.

- [x] Rewrite `.gitignore` (Python, Node, Django, env, IDE, OS).
- [x] `git rm -r --cached` on `__pycache__/`, `frontend/.next/`, `backend/staticfiles/`, `*.pyc`, `.env.local`.
- [x] Rotate the leaked `SECRET_KEY` and `DB_PASSWORD=12345`; never re-commit real env files.
- [x] Add root `README.md` with architecture diagram, quickstart, tech stack.
- [x] Add `LICENSE`, `docs/` index, and delete orphan `frontend/src/styles/globals.css`.
- [x] First meaningful commit with a conventional-commit message.

**Done when:** `git ls-files` contains no build output, no `.env.local`; a fresh clone + documented steps boots both apps.

**Completed 2026-10-09** — commit `8b2d267`, pushed to `origin/main`.

| Check | Before | After |
|---|---|---|
| Tracked files | 563 (445 artifacts) | **121** (119 source + 2 `.env.example`) |
| `__pycache__` / `.next` / `staticfiles` / `.pyc` | 443 | **0** |
| `.env.local` tracked | 2 | **0** (still on disk for local dev) |
| `.gitignore` | 1 line | 110 lines |
| Root `README.md` / `LICENSE` / `docs/README.md` | absent | added |
| Working tree | 564 unstaged entries | clean, matches `origin/main` |
| Secrets in history | n/a | none — repo had zero commits; scan of tracked files found no keys |

Notes:
- "Rotate secrets" was a **no-op for history** — with zero prior commits, no secret had ever been persisted. `.env.local` was staged but never committed, so untracking was sufficient; both files remain on disk. Real rotation (env-file loader + fail-fast defaults) is **Phase 2**.
- `backend/static/` (source CSS + admin template) was deliberately **kept**; only `backend/staticfiles/` (collectstatic output) was dropped.
- Removed orphan `frontend/src/styles/globals.css` (1.2 KB, zero imports).

---

## Phase 2 — Environment & configuration management
**Goal:** env files actually drive configuration; defaults are safe.

- [ ] Load env files at startup (finish the unused `python-decouple`, or add `django-environ`/`python-dotenv`).
- [ ] Make `EMAIL_BACKEND` env-driven (currently hardcoded to console at `settings.py:166`).
- [ ] Fail fast in production: require `SECRET_KEY`, refuse insecure default; `DEBUG` defaults to `False`.
- [ ] Remove duplicate `AUTH_USER_MODEL` (`settings.py:88` and `:181`).
- [ ] Add `LOGGING` config with request/error handlers; remove `str(e)` leakage in `payments/views.py:114-118, 180-184`.
- [ ] Frontend: validate `NEXT_PUBLIC_*` at boot; drop the localhost fallback in `next.config.js`.

**Done when:** `.env.example` documented and complete; app refuses to start in prod with missing secrets.

---

## Phase 3 — Test infrastructure (backend)
**Goal:** a real test suite that runs and gates changes.

- [ ] Add `pytest`, `pytest-django`, `factory_boy`, `coverage` to `requirements.txt`.
- [ ] Add `pytest.ini`/`pyproject.toml` + `conftest.py` with DB, client, and auth fixtures.
- [ ] Make tests run on SQLite or a dedicated Postgres test DB by default (no dependency on dev DB).
- [ ] Add per-app `tests/` package: `test_users.py`, `test_stores.py`, `test_products.py`, `test_inventory.py`, `test_orders.py`, `test_payments.py`.
- [ ] Seed Phase 6 defect repros as failing-first tests (checkout rollback, oversell, double-pay, privilege escalation).
- [ ] Coverage reporting with a floor (start at 60%, ratchet upward).

**Done when:** `pytest` runs green with real assertions; coverage report generated.

---

## Phase 4 — Test infrastructure (frontend) + lint
**Goal:** lint and unit tests exist and pass.

- [ ] Add `.eslintrc.json` extending `next/core-web-vitals`; align `eslint-config-next` to the Next 14 line.
- [ ] Add Prettier + `.editorconfig`.
- [ ] Add Vitest + `@testing-library/react` + jsdom; write tests for `AuthContext`, `lib/api.js` interceptors, `ProductCard`, cart math.
- [ ] Add `npm test` and `npm run test:coverage` scripts.
- [ ] Fix all lint errors found by the newly working linter.

**Done when:** `npm run lint` exits 0 non-interactively; `npm test` is green.

---

## Phase 5 — CI/CD pipeline
**Goal:** every push is automatically verified.

- [ ] `.github/workflows/ci.yml` — backend job (deps, migrate, lint, pytest) + frontend job (npm ci, lint, test, build).
- [ ] Cache pip/npm; matrix over Python/Node versions.
- [ ] Post coverage to the PR; block merge on failure.
- [ ] Add a release workflow (`backend` + `frontend` versioned tags).
- [ ] Add pre-commit hooks (`pre-commit` + lint-staged).

**Done when:** a PR shows green checks; a broken test blocks merge.

---

## Phase 6 — Critical transactional correctness
**Goal:** money and stock are never wrong. *Highest-value phase.*

- [ ] **Fix checkout rollback:** replace `return Response(...)` inside `transaction.atomic()` (`orders/views.py:203-206, 218-221`) with raised, caught-outside exceptions.
- [ ] **Fix oversell race:** use `select_for_update()` / `F()` expressions in `inventory/services.py:18-41, 44-67, 70-107` (currently zero `select_for_update`/`F(` in the repo).
- [ ] **Fix double payment:** stop paying at checkout *and* again from `checkout/page.js:156`; make one authoritative path.
- [ ] **Fix payment race:** lock the order row (`select_for_update`) before reading `payment_status` (`payments/views.py:62-82`); add an idempotency key.
- [ ] **Revalidate price at checkout** — currently charges `price_at_time_of_addition` (`orders/views.py:169`).
- [ ] Validate stock at `cart/add` time, not only at checkout.

**Done when:** concurrency tests prove no oversell, no double-charge, no partial commit.

---

## Phase 7 — Authorization & security hardening
**Goal:** no privilege escalation, no brute force, real HTTPS posture.

- [ ] Make `is_seller` read-only in `UserSerializer` (and audit every serializer's writable fields).
- [ ] Extract a reusable `IsSeller` permission class (currently `if not user.is_seller` copy-pasted 8+ times).
- [ ] Add DRF throttling: strict on `login`/`register`/`password-reset`, scoped elsewhere.
- [ ] Add `SECURE_*`, HSTS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` when not `DEBUG` (README claims HTTPS enforcement that does not exist).
- [ ] Blacklist refresh tokens on password change (currently not done).
- [ ] Add account lockout / failed-login backoff; add audit log for auth events.
- [ ] Decide JWT storage: move to `HttpOnly` cookies (as README claims) or drop the claim.

**Done when:** escalation test fails to promote itself; login is rate-limited; `check --deploy` is clean.

---

## Phase 8 — Email verification & password recovery
**Goal:** users can actually sign up and recover access.

- [ ] Remove the duplicate email flow (`users/views.py:28-39` **and** `users/signals.py:10-48` send two different links).
- [ ] Delete dead `EmailVerificationToken` model *or* use it consistently — one flow only.
- [ ] Build the missing `/verify-email/[uidb64]/[token]/` page (emails currently link to a 404).
- [ ] Fix `api.js:72` — `verifyEmail` must pass both `uidb64` and `token`.
- [ ] Add forgot/reset password endpoints + `/forgot-password` and `/reset-password` pages.
- [ ] Make email sending non-fatal (currently `fail_silently=False` after user save → HTTP 500 on SMTP failure).

**Done when:** register → receive one email → click → verify → login works end-to-end.

---

## Phase 9 — Consistent API contract & OpenAPI docs
**Goal:** one error shape, machine-readable docs.

- [ ] Add a custom DRF `EXCEPTION_HANDLER` returning `{code, message, details, request_id}` everywhere.
- [ ] Remove hand-rolled `{'error': ...}` dicts from function views; align on the envelope.
- [ ] Install `drf-spectacular`; add `/api/docs/` (Swagger) and `/api/redoc/` — **README promises these and they don't exist.**
- [ ] Add schema-driven examples, tags, and auth annotations on all 51 routes.
- [ ] Add `Idempotency-Key` support on money-moving endpoints.
- [ ] Publish an error-code reference in `docs/`.

**Done when:** `/api/docs/` renders with every route; a 404, 400, 401, 403, 429, 500 all share one shape.

---

## Phase 10 — N+1 elimination & query performance
**Goal:** list endpoints stay fast as data grows.

- [ ] `select_related`/`prefetch_related` on product, order, and store list queries.
- [ ] Fix `ProductListSerializer.get_primary_image` / `get_is_wishlisted` (`products/serializers.py:151-160`).
- [ ] Cache `total_stock` / `average_rating` / `review_count` (`products/models.py:32-56` — each runs a query per row).
- [ ] Fix `search_products` (`products/views.py:145-148`): it evaluates the full queryset in Python, then re-queries; make it DB-side + paginated.
- [ ] Fix `low_stock_items` (`inventory/views.py:103-108`) to filter in SQL; route `store_analytics` (`stores/views.py:161-183`) which is defined but unreachable.
- [ ] Add `django-debug-toolbar` + `silk` for profiling; assert a query-count ceiling in tests.

**Done when:** a 20-row list renders in a bounded number of queries (asserted in tests).

---

## Phase 11 — Correct business features (analytics, refunds, status machine)
**Goal:** stop showing fake numbers; make refunds safe.

- [ ] **Order status state machine** with allowed transitions (`orders/views.py:270-307` accepts any→any).
- [ ] Return inventory on cancel/refund — `inventory/services.return_inventory_for_order` exists and is **never called**.
- [ ] Refund must reverse the commission ledger and mark the original transaction refunded (currently a negative `SUCCESSFUL` transaction with no reversal).
- [ ] Fix `stores/views.py:144` reading `COMPLETED`, a status that doesn't exist in `Order.STATUS_CHOICES`.
- [ ] Replace fabricated metrics (`conversion_rate: 3.2`, `total_views: products.count() * 87` at `stores/views.py:154-155`) with real tracked data.
- [ ] Remove the bare `except: pass` at `stores/views.py:112-118`.
- [ ] Expose the refund endpoint in the UI (`paymentsAPI.refund` is never called).

**Done when:** cancel/refund restocks inventory; dashboard metrics derive from real rows.

---

## Phase 12 — Product images & media pipeline
**Goal:** products show real images.

- [ ] Fix the field mismatch: `ProductCard.js:9` reads `images[0].image_url`, serializer exposes `primary_image` → **every card 404s today**.
- [ ] Create `frontend/public/` with `placeholder-product.jpg`, `placeholder-store.jpg`, favicon, `robots.txt`, `sitemap.xml`, web manifest (referenced but missing → all 404).
- [ ] Adopt `next/image` (currently zero usage) with a tightened `images.remotePatterns` (config currently allows *any* `https://**` host).
- [ ] Add real file storage: `ImageField`/`FileField` + upload endpoints (backend has **no file fields at all**).
- [ ] Add upload widgets to seller product create/edit and store setup (currently no image field in forms).
- [ ] Image validation: size, MIME, virus scan hook; generate thumbnails.

**Done when:** a seller uploads a photo and it renders on the product card, list, and detail pages.

---

## Phase 13 — Search, filtering & pagination UX
**Goal:** customers can find things.

- [ ] Backend: DB-backed full-text/trigram search with ranking; paginate `search/` and `featured/` (function views bypass DRF pagination today).
- [ ] Honor the `in_stock` filter already sent by `products/page.js:36` (currently ignored).
- [ ] Add facets: category, price range, rating, store, verified-seller.
- [ ] Frontend: add `next/previous` pagination controls (`next`/`previous` are ignored; only page 1 renders).
- [ ] Debounced search UI + `/search` results page wired to `productsAPI.search` (client function exists but is never called).
- [ ] Add `Product.slug` for SEO-friendly URLs (currently `/products/<id>`).

**Done when:** large catalog is searchable, filterable, and pageable end-to-end.

---

## Phase 14 — Coupons, tax & shipping engine
**Goal:** realistic order economics.

- [ ] New `coupons` app: code, type (%/flat), min order, usage limits, per-user caps, expiry, stacking rules, abuse prevention.
- [ ] Shipping: zones, methods, rate calculation, free-shipping thresholds; replace the `shipping_method` free-text field.
- [ ] Tax calculation (region-aware or simplified VAT/GST) included in totals.
- [ ] Order totals recomputed server-side from coupon + shipping + tax; never trust the client.
- [ ] Frontend: coupon input at checkout, shipping method picker, itemized totals.
- [ ] Tests for edge cases: expired, exhausted, over-stacking, negative-total clamping.

**Done when:** a coupon + shipping + tax checkout produces a correct, tested order total.

---

## Phase 15 — Notifications & async work
**Goal:** users and sellers get told things.

- [ ] Add Celery + Redis (or `django-q2`) with a beat scheduler; make settings env-driven.
- [ ] Emails: order placed, status changed, shipped (with tracking), refunded, low-stock alert, password reset.
- [ ] In-app notification model + bell UI in `Header.js`.
- [ ] Wrap existing verification email in a task; retry with exponential backoff.
- [ ] Low-stock and payout-run scheduled jobs.
- [ ] A dev fallback that runs tasks eagerly so local setup stays simple.

**Done when:** placing an order dispatches an async email; tasks are retry-safe and idempotent.

---

## Phase 16 — Frontend architecture & rendering quality
**Goal:** fast, resilient, SEO-friendly pages.

- [ ] Add `app/loading.js`, `app/error.js`, `app/not-found.js`, and a root error boundary (**none exist**).
- [ ] Convert product/store/list pages to Server Components with `generateMetadata`; add OpenGraph/Twitter cards and JSON-LD for products.
- [ ] Add `middleware.js` for route protection (all 19 pages are client components with `useEffect` redirects → data flash, trivially bypassed).
- [ ] Add data-fetching with SWR/React Query: caching, revalidation, and consistent `isLoading`/`error` states (today errors surface only as toasts).
- [ ] Standardize the API error fallback (`checkout/page.js:173-177` already has an ad-hoc 3-way branch).
- [ ] Route-level code splitting audit; remove `clean-cache.ps1`.

**Done when:** product pages are SSR'd with metadata, have loading/error boundaries, and protected routes redirect server-side.

---

## Phase 17 — Accessibility & design-system polish
**Goal:** usable by everyone, consistent everywhere.

- [ ] Full a11y pass: landmarks, headings hierarchy, focus management, skip-link, contrast ratios (zero `aria-*` attributes exist in `src`).
- [ ] Make the `Header.js:84` hover dropdown keyboard-accessible (focus trap, `group-focus`, Escape to close).
- [ ] Icon-only buttons need `aria-label`, not just `title=`.
- [ ] Honor `prefers-reduced-motion` in all `framer-motion` animations.
- [ ] Extract shared form primitives (input/select/error) — currently duplicated across 19 pages.
- [ ] Skeleton/empty-state consistency; toast usage policy.
- [ ] Wire up a11y CI: `eslint-plugin-jsx-a11y` (comes with `next/core-web-vitals`) + `axe-core` smoke tests.

**Done when:** Lighthouse a11y ≥ 95; keyboard-only navigation works across the whole app.

---

## Phase 18 — Admin, moderation & seller tools
**Goal:** operators can run the marketplace without SQL.

- [ ] Register `ProductReview`, `Wishlist`, `StoreFollower` in Django admin (reviews/wishlist are unregistered today).
- [ ] Review moderation: `is_approved` defaults to `True` — flip to pending + add approve/reject endpoints and a queue UI.
- [ ] Wire up or delete `StoreFollower` (model + migration exist with **zero** API) — and decide on other dead code.
- [ ] Seller analytics: replace mocked stats with views, revenue time-series, top products, conversion funnel.
- [ ] Add attribute/variant management UI (variants exist in the model but are unusable from forms).
- [ ] Payout runs: allow ledger `payout_status` to reach `PAID` (currently impossible via any endpoint).

**Done when:** an operator can moderate a review and a seller can see real analytics in the dashboard.

---

## Phase 19 — Documentation, DevOps & packaging
**Goal:** one command to run; one command to ship.

- [ ] `Dockerfile` for backend + frontend, `docker-compose.yml` with Postgres (and Redis from Phase 15).
- [ ] `Makefile` / scripts: `make dev`, `make test`, `make lint`, `make seed`, `make db`.
- [ ] Convert the 6 root helper scripts into proper management commands — `manage.py seed_demo` (from `create_test_data.py`) and `manage.py repair_inventory`.
- [ ] **Delete the destructive `fix_inventory.py`** (force-resets any legitimate 0-stock row to 100) and the duplicate `setup_database.py` / `complete_setup.py` / `complete_fix.py`.
- [ ] Fix `backend/README.md` — remove false claims: `/api/docs/` doesn't exist, HttpOnly cookies aren't used, HTTPS isn't enforced, tests don't exist, WhiteNoise isn't installed, `createdb markethub_db` should be `markethub`, product routes are wrong, `verify-email` needs two params.
- [ ] Add `CHANGELOG.md`, `docs/api.md`, `docs/architecture.md`, `docs/deployment.md` (Render/Railway/Neon per README).

**Done when:** `docker compose up` yields a working stack; README has zero false statements.

---

## Phase 20 — Production deployment, observability & release
**Goal:** ship it and know when it breaks.

- [ ] Staging + production environments with separate secrets; `DEBUG=False`, `ALLOWED_HOSTS` verified.
- [ ] Error tracking (Sentry) for backend and frontend; source maps uploaded.
- [ ] Structured logging + request IDs propagated from Phase 9; log aggregation.
- [ ] Metrics/alerting: error rate, p95 latency, 5xx, queue depth, DB connections, low-stock.
- [ ] Load test critical paths (browse, search, checkout) with `locust`/`k6`; fix what breaks.
- [ ] Backup + restore runbook for Postgres; verify a real restore.
- [ ] Security pass: dependency audit (`pip-audit`, `npm audit`), OWASP top-10 review, secrets scan in CI.
- [ ] Incident runbook, status page, and a rollback procedure; cut `v1.0.0`.

**Done when:** the site is live behind HTTPS with dashboards, alerts, tested backups, and a documented rollback.

---

## Suggested sequencing

| Wave | Phases | Rationale |
|---|---|---|
| **Foundation** | 1 → 2 → 3 → 4 → 5 | Clean repo, config, tests, lint, CI — everything after this is safer |
| **Correctness** | 6 → 7 → 8 → 9 → 10 | Money, security, onboarding, contract, performance |
| **Capability** | 11 → 12 → 13 → 14 → 15 | Real features replace mocks and dead code |
| **Polish** | 16 → 17 → 18 | UX, a11y, admin |
| **Ship** | 19 → 20 | Package, document, deploy, observe |

**Current test status:** backend `0 tests`, frontend `no test runner` — Phases 3–5 are the highest-leverage starting point, because Phases 6–11 are regression-prone without them.
