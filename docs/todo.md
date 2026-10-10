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
| No location model | `Address` has free-text `city` / `state_province` / `postal_code`, no wilaya/commune | 11 |
| No currency / i18n | `LANGUAGE_CODE='en-us'`, `TIME_ZONE='UTC'`, no currency field; frontend has no i18n | 11 |
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
1. `orders/views.py` `add_to_cart`: `Product.objects.get(...)` is unguarded → **HTTP 500** on unknown product (should be 404). Also never checks `is_available` or stock.
2. `orders/views.py` `update_cart_item`: `int(quantity)` on non-numeric input → **HTTP 500**.
3. `orders/views.py` `checkout`: `Address.objects.get(...)` is outside the validation path → 500 if the address is missing/not the user's.
4. Failed-payment branch returns **inside** `atomic()` *after* `order.payment_status='FAILED'` is saved → a FAILED order is committed with its stock still reserved (same root cause as defect 1, different symptom).
5. `settings.py` declares `AUTH_COOKIE*` keys under `SIMPLE_JWT`. These are **not SimpleJWT options** (no cookie auth is built in), so they do nothing and give a false sense of HttpOnly security.
6. `settings.py` ends with a duplicate `AUTH_USER_MODEL` (already tracked), plus `DB_PASSWORD` defaults to `'12345'` and `DEBUG` defaults to `True`.
7. `User` has no unique/validated `phone_number`, which is the *primary identity* in the Algerian market.

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

## Phase 3 — Test infrastructure (backend)
**Goal:** a real test suite that gates changes.

- [ ] `pytest`, `pytest-django`, `factory_boy`, `coverage`, `pytest-xdist`.
- [ ] `pytest.ini` + `conftest.py` (DB, API client, auth, seller/buyer/store factories).
- [ ] Tests run against a dedicated Postgres test DB (**not SQLite**: you will rely on Postgres FTS, `select_for_update`, and trigram in later phases).
- [ ] Per-app `tests/` packages.
- [ ] Failing-first tests for every defect in the original list **and** §0.3 (rollback, oversell, double-pay, privilege escalation, 500s on bad input).
- [ ] Coverage floor 60%, ratchet to 80% on `orders`, `payments`, `inventory`.

**Done when:** `pytest` is green with real assertions; coverage report is generated.

---

## Phase 4 — Test infrastructure (frontend) + lint
**Goal:** lint and unit tests exist and pass.

- [ ] `.eslintrc.json` extending `next/core-web-vitals`; fix the `eslint-config-next@16` vs `next@14` mismatch.
- [ ] Prettier + `.editorconfig`.
- [ ] Vitest + Testing Library + jsdom: `AuthContext`, `lib/api.js` interceptors, `ProductCard`, cart math.
- [ ] Playwright for 3 smoke journeys: register → login, post a listing, search → open listing.
- [ ] `npm test`, `npm run test:coverage`, `npm run lint` (non-interactive).

**Done when:** `npm run lint` exits 0; `npm test` is green; Playwright smoke passes locally.

---

## Phase 5 — CI/CD pipeline
**Goal:** every push is verified.

- [ ] `.github/workflows/ci.yml`: backend (deps, migrate, lint, pytest, `check --deploy`) + frontend (ci, lint, test, build).
- [ ] Cache pip/npm; Postgres service container.
- [ ] Coverage on PRs; protected `main` branch; required checks.
- [ ] Secret scanning + `pip-audit` + `npm audit` in CI (moved up from Phase 20).
- [ ] Pre-commit hooks; Dependabot.
- [ ] Preview deployments per PR (optional but valuable for design review).

**Done when:** a PR shows green checks; a broken test blocks merge.

---

## Phase 6 — Critical transactional correctness
**Goal:** money and stock are never wrong. *Highest-risk code in the repo.*

- [ ] **Fix checkout rollback:** no `return` inside `transaction.atomic()` (`orders/views.py` stock-failure and payment-failure branches). Raise a domain exception, catch it *outside* the atomic block. Covers the FAILED-order-with-reserved-stock bug (§0.3 #4).
- [ ] **Fix oversell race:** `select_for_update()` / `F()` in `inventory/services.py`.
- [ ] **One authoritative payment path** (checkout page currently pays again from `checkout/page.js:156`).
- [ ] **Lock order row** before reading `payment_status`; add idempotency keys.
- [ ] **Re-validate price at checkout** (currently uses `price_at_time_of_addition`); show "price changed" UX.
- [ ] Validate existence, `is_available`, and stock at `cart/add` and `cart/update` (fixes §0.3 #1, #2).
- [ ] Guard `Address` lookup in checkout (§0.3 #3).
- [ ] Move order creation into a `orders/services.py` `place_order()` function. Views stay thin; the logic is unit-testable.

**Done when:** concurrency tests prove no oversell, no double charge, no partial commit; no endpoint returns 500 on bad input.

---

## Phase 7 — Authorization & security hardening
**Goal:** no privilege escalation, no brute force, real HTTPS posture.

- [ ] `is_seller` read-only in `UserSerializer`; audit all serializers for writable sensitive fields.
- [ ] Reusable `IsSeller` / `IsStoreOwner` / `IsListingOwner` permission classes.
- [ ] DRF throttling: strict on login/register/OTP/password-reset; **scoped throttle on "reveal phone number"** (anti-scraping; Ouedkniss-style sites are scraped heavily).
- [ ] `SECURE_*`, HSTS, secure cookies when not `DEBUG`.
- [ ] Blacklist refresh tokens on password change; failed-login backoff; auth audit log.
- [ ] **Decide JWT storage:** HttpOnly cookie (needs a custom auth class + CSRF handling) or bearer tokens. The README claim must match reality.
- [ ] Object-level permission tests for every write endpoint (IDOR checks).
- [ ] Upload security rules reserved for Phase 14 (MIME sniffing, size, EXIF stripping).

**Done when:** escalation test fails; login is rate-limited; `check --deploy` is clean.

---

## Phase 8 — Identity: email, **phone OTP**, password recovery
**Goal:** reliable identity, which is the base of trust. In Algeria, **phone is the primary identity**.

- [ ] Remove the duplicate email flow (`users/views.py` **and** `users/signals.py` both send links); delete or use `EmailVerificationToken`: one flow only.
- [ ] Build the missing `/verify-email/[uidb64]/[token]/` page; fix `api.js` `verifyEmail` params.
- [ ] Forgot/reset password endpoints + pages. Make email sending non-fatal (no 500 on SMTP failure).
- [ ] **Phone verification by OTP** (SMS via a local-friendly provider, with a pluggable `SmsBackend`; fallback to WhatsApp/Viber business API if cheaper). Normalize numbers to E.164 (`+213…`), unique constraint on verified numbers.
- [ ] Allow **phone-first signup/login** (email optional).
- [ ] OTP rate limits, expiry, attempt caps; per-number and per-IP daily limits (SMS pumping defense).
- [ ] Optional social login (Google, Facebook), since Facebook is dominant in Algeria.

**Done when:** a new user can register with just a phone, verify by OTP, log in, and recover access end-to-end.

---

## Phase 9 — Consistent API contract & OpenAPI docs
**Goal:** one error shape, machine-readable docs.

- [ ] Custom `EXCEPTION_HANDLER`: `{code, message, details, request_id}`.
- [ ] Replace hand-rolled `{'error': …}` dicts; translate messages (ar/fr/en) via `Accept-Language`.
- [ ] `drf-spectacular` at `/api/docs/` and `/api/redoc/`; tag all routes.
- [ ] `Idempotency-Key` support on money-moving and listing-create endpoints.
- [ ] API versioning (`/api/v1/`) **before** a mobile app depends on it.
- [ ] Error-code reference in `docs/`.

**Done when:** `/api/docs/` lists every route; 400/401/403/404/429/500 share one shape.

---

## Phase 10 — N+1 elimination & query performance
**Goal:** list endpoints stay fast at 100k+ listings.

- [ ] `select_related` / `prefetch_related` on listing, order, store lists.
- [ ] Replace per-row `total_stock`, `average_rating`, `review_count` properties with annotations or denormalized, signal-updated columns.
- [ ] Fix `ProductListSerializer.get_primary_image` / `get_is_wishlisted`.
- [ ] Fix `search_products` (evaluates the whole queryset in Python) and `low_stock_items` (filter in SQL); make `store_analytics` reachable.
- [ ] **Keyset (cursor) pagination** for infinite-scroll feeds (offset pagination degrades badly at scale).
- [ ] Composite indexes for the real access patterns (category + wilaya + status + `-published_at`).
- [ ] `django-debug-toolbar`/`silk` in dev; **query-count ceiling asserted in tests**.

**Done when:** a 20-row list renders in a bounded number of queries, asserted in tests.

---

## Phase 11 — Algeria localisation: language, RTL, currency, geography *(new)*
**Goal:** feels native to Algerian users from the first screen.

- [ ] **Frontend i18n** (`next-intl`): Arabic, French, English; language switcher; persisted preference.
- [ ] **RTL layout** with Tailwind logical properties (`ms-*`, `me-*`, `ps-*`, `start-*`); test every page in RTL.
- [ ] Arabic-friendly font stack with a fallback; Eastern/Western digit handling.
- [ ] **Currency:** DZD as the default; display with correct grouping; keep the "Algerian habit" of quoting prices in **millions/old centimes** in mind (e.g. "1 million" = 10,000 DA). Offer a configurable price display.
- [ ] **Geography models:** `Wilaya` and `Commune` (code, name_ar, name_fr, name_en, optional lat/lng) loaded from a data fixture. Make it data-driven and **verify against the current official administrative list**, as wilaya counts have been changing.
- [ ] Replace free-text `Address.city/state_province/postal_code` with FK to `Wilaya`/`Commune` + free-text street line.
- [ ] Location picker component (wilaya → commune) usable in listing forms, filters, and addresses.
- [ ] Backend translation of enums/status labels and emails.

**Done when:** the full app works in ar (RTL), fr, and en; a listing can be tied to a wilaya/commune; prices render in DZD.

---

## Phase 12 — Category tree & dynamic attributes *(new)*
**Goal:** every category has the right form and the right filters (this is where classifieds sites win or lose).

- [ ] `Category` model: tree (`django-mptt`/`treebeard` or `ltree`), slug, translated names, icon, order, `is_active`.
- [ ] `AttributeDefinition` per category: key, label (i18n), type (text/number/enum/boolean/year/range), required, filterable, unit, choices.
  Examples: **Vehicles** (brand, model, year, km, fuel, gearbox, papers) · **Real estate** (type, rooms, m², floor, deal type) · **Phones** (brand, storage, condition) · **Jobs** (contract, experience, salary).
- [ ] Store values in validated `JSONB` (`attributes_json` already exists, so formalize it) with GIN indexes; validate against definitions.
- [ ] Migrate `Product.category` (free text) and `Store.category` (hardcoded choices) to FKs; data migration for existing rows.
- [ ] Dynamic listing form + dynamic filter sidebar generated from definitions.
- [ ] Seed the launch categories first (Phase 29), not all of Ouedkniss's.
- [ ] Admin UI to edit categories/attributes without a deploy.

**Done when:** adding a category + attributes in admin instantly yields the posting form and filters in the UI.

---

## Phase 13 — Listings model: individuals, stores, and ad lifecycle *(new)*
**Goal:** anyone can post in under 90 seconds; stores keep rich features.

- [ ] **Decision (Phase 0):** evolve `Product` into `Listing` (recommended) with `seller` FK to `User`, **nullable `store`**, and `listing_type` (`FOR_SALE`, `STORE_PRODUCT`, `SERVICE`, `JOB`, `RENT`, `WANTED`).
- [ ] Price modes: `FIXED`, `NEGOTIABLE`, `ON_REQUEST`, `FREE`, `EXCHANGE`; currency; optional old price.
- [ ] **Lifecycle:** `DRAFT → PENDING_REVIEW → ACTIVE → EXPIRED / SOLD / REJECTED / ARCHIVED`; expiry (e.g. 30 days), **renew**, mark-as-sold, auto-pause.
- [ ] Contact mode per listing: show phone / WhatsApp / chat-only / checkout-enabled.
- [ ] **Fast posting wizard:** category → photos → 3–5 fields → location → price → publish. Autosave drafts; works on slow mobile networks.
- [ ] **Duplicate-listing detection** (same seller + similar title/price/image hash).
- [ ] Per-user active-listing quotas by tier (free vs verified vs store plan).
- [ ] Keep cart/checkout only for `STORE_PRODUCT` with inventory; classifieds skip inventory.
- [ ] Slug URLs: `/l/<slug>-<id>` (SEO + sharing); canonical redirect when slug changes.
- [ ] "Similar listings" and "more from this seller".

**Done when:** an unauthenticated visitor can register and publish a listing in ≤ 90 s; listings expire and renew correctly; a store can still sell with inventory + checkout.

---

## Phase 14 — Media pipeline *(was Phase 12)*
**Goal:** fast, safe, real images.

- [ ] Fix `ProductCard.js` reading `image_url` while the serializer exposes `primary_image` (every card is broken today).
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
- [ ] Fix `stores/views.py` reading status `COMPLETED`, which doesn't exist; remove bare `except: pass`.
- [ ] Replace fabricated metrics (`conversion_rate: 3.2`, `views = count * 87`) with real tracked data.
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
| 4 | JWT storage | **HttpOnly cookie + CSRF** for web; bearer for the future mobile app (versioned API). |
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
**Current status:** Phases 0–2 ✅ · everything else open · backend `0 tests`, frontend `no test runner`. Phases 3–5 remain the highest-leverage starting point.
