# MarketHub

An open-source marketplace platform — multi-vendor stores, product catalog, cart & checkout, inventory tracking, reviews, wishlist, and simulated payments.

**Stack:** Django REST Framework · PostgreSQL · Next.js 14 (App Router) · Tailwind CSS

---

## Status

MarketHub is **under active development**. The core commerce flows work end-to-end, but the project is not yet production-ready.

| Area | State |
|---|---|
| Backend | 7 apps · 64 API paths / 76 operations · migrations in sync |
| Frontend | 22 pages (Next.js App Router) |
| Tests | Backend: **403 passing** (1 strict xfail pinning a known defect) · Frontend: **83 unit + 5 e2e passing** |
| CI | **GitHub Actions** — backend, frontend and security-audit jobs on every push/PR |
| API docs | **Swagger** at `/api/docs/`, ReDoc at `/api/redoc/` — generated from drf-spectacular (0 schema errors) |

The full 29-phase plan to close these gaps lives in **[docs/todo.md](docs/todo.md)**.

---

## Repository layout

```
MarketHub/
├── backend/                 # Django project
│   ├── core/                # settings, root urls, wsgi/asgi
│   ├── apps/
│   │   ├── users/           # auth, profiles, addresses (wilaya/commune FKs)
│   │   ├── geography/       # Wilaya & Commune reference data (69 wilayas)
│   │   ├── stores/          # seller stores & followers
│   │   ├── products/        # catalog, reviews, wishlist
│   │   ├── inventory/       # stock levels & audit log
│   │   ├── orders/          # cart, checkout, order lifecycle
│   │   └── payments/        # transactions, refunds, commissions
│   ├── locale/              # gettext catalogs (fr, ar)
│   ├── static/              # source static assets
│   ├── templates/           # Django templates
│   ├── manage.py
│   └── requirements.txt
├── frontend/                # Next.js 14 app
│   └── src/
│       ├── app/             # App Router pages
│       ├── components/      # common / product components
│       ├── context/         # AuthContext
│       ├── i18n/            # locale config + ar/en/fr message catalogues
│       └── lib/             # axios client, API services, currency/geography
├── docs/                    # roadmap & documentation
└── .gitignore
```

---

## Prerequisites

- **Python** 3.10+
- **Node.js** 18+ (20 LTS recommended)
- **PostgreSQL** 13+
- **Git**

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/abderaoufsec/MarketHub.git
cd MarketHub
```

### 2. Backend

```bash
cd backend

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a database and configure it:

```bash
createdb markethub          # note: settings default DB_NAME is 'markethub'
```

Copy the example environment file and edit the values:

```bash
cp .env.example .env.local
```

Run migrations and start the server:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API is now at <http://localhost:8000> — root routes:

| Prefix | App |
|---|---|
| `/api/v1/auth/` | users — register, login, logout, profile, addresses |
| `/api/v1/geography/` | geography — wilayas, communes (public read-only reference data) |
| `/api/v1/stores/` | stores — public store list/detail, seller store management |
| `/api/v1/products/` | products — catalog, reviews, wishlist |
| `/api/v1/inventory/` | inventory — stock, low-stock, audit log |
| `/api/v1/orders/` | orders — cart, checkout, order history |
| `/api/v1/payments/` | payments — transactions, refunds, commissions |
| `/api/docs/` · `/api/redoc/` | interactive OpenAPI documentation (schema: `/api/schema/`) |

The whole API is versioned at `/api/v1/` (Phase 9). Failures return a single
envelope — `{code, message, details, request_id}` — and every `code` is
listed in **[docs/error-codes.md](docs/error-codes.md)**.

List endpoints are paginated (Phase 10). The endless feeds — the catalogue,
search, stores, reviews, the wishlist, the inventory audit log — are **keyset
paginated**: follow `next` for the next page and pass `?page_size=` (max 100)
to change how much comes back. Those pages carry no `count`, because counting
a feed is an O(n) scan of everything before the last row. Endpoints where
people jump around instead (order history, transactions, a seller's
inventory) keep `?page=`.

> **Environment variables:** `backend/core/settings.py` reads configuration with **python-decouple**, in this order: real process environment variables → `backend/.env.local` → `backend/.env`. Copy `.env.example` to `.env.local` (see the table in `.env.example` for every variable). With `DEBUG=False` the app refuses to start until `DJANGO_SECRET_KEY` and `DB_PASSWORD` hold real values.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App is now at <http://localhost:3000>.

Point it at the backend by creating `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### 4. Verify

```bash
# Backend — system checks
cd backend && python manage.py check

# Backend — lint & format (ruff; config in backend/ruff.toml)
ruff check .
ruff format --check .

# Backend — tests (pytest-django; creates a test_<DB_NAME> Postgres database)
python -m pytest
coverage report --fail-under=60
coverage report --include="apps/orders/*,apps/payments/*,apps/inventory/*" --fail-under=80

# Frontend — lint, format check, unit tests
cd ../frontend
npm run lint
npm run format:check
npm test            # Vitest + Testing Library (jsdom)
npm run test:coverage
npm run build       # production build (needs NEXT_PUBLIC_API_URL)

# Frontend — Playwright smoke journeys (register → login, post a listing,
# search → open listing). Starts Django + `next dev` itself and seeds the
# e2e fixtures via `python manage.py seed_e2e`; needs a migrated Postgres DB.
npx playwright install chromium   # once
npm run e2e
```

> The backend suite pins 1 known defect as `xfail(strict=True)` (see [docs/todo.md](docs/todo.md) §0.3): it is expected to fail until Phase 17 fixes it, and the suite turns red the moment a fix lands so the marker gets removed.

### 5. Optional: git hooks

```bash
pip install -r backend/requirements-dev.txt
pre-commit install          # lint/format on every commit
pre-commit install --hook-type pre-push   # also run the test suites
```

---

## Continuous integration

Every push and pull request runs `.github/workflows/ci.yml`:

| Job | What it gates |
|---|---|
| **Backend (Django)** | `ruff check` + `ruff format --check`, `manage.py check`, `makemigrations --check`, pytest, 60% overall coverage floor, 80% ratchet on `orders`/`payments`/`inventory`, `check --deploy` |
| **Frontend (Next.js)** | `npm run lint`, `format:check`, Vitest with coverage, `next build` |
| **Security audits** | gitleaks secret scan (blocking); `pip-audit` + `npm audit` (advisory until triaged) |

Dependabot opens weekly PRs for pip, npm and GitHub Actions dependencies.

> **Manual setup step:** branch protection on `main` (require PR, require the three checks above) must be enabled in the GitHub UI — see [docs/todo.md](docs/todo.md) Phase 5.

---

## Key concepts

### Auth
- JWT access/refresh tokens via SimpleJWT, with rotation and blacklisting on logout.
- **HttpOnly cookie session (Phase 7):** the JWT pair lives in `HttpOnly` + `SameSite` cookies set by the server — tokens never appear in response bodies and never touch JavaScript. Unsafe requests authenticated this way must echo the readable `csrftoken` cookie as `X-CSRFToken` (`GET /api/v1/auth/csrf/` bootstraps it); `Authorization: Bearer` still works for API/mobile clients. A readable `mh_session` hint flag tells the SPA whether to attempt a session restore.
- Auth endpoints are rate-limited, failed logins back off exponentially per (IP, email), password changes revoke every other session, and an `AuthEvent` audit trail records logins/failures/logout/password changes.
- Role-based access: buyers and sellers share one `User` model with an `is_seller` flag (read-only on profile updates — sellers opt in at registration).
- Email verification tokens on registration.

### Commerce flow
1. Seller creates a store, then products.
2. `Inventory` rows track stock per product/variant, with an `InventoryAuditLog` trail. Stock is checked when a buyer adds to or changes the cart, and reserved under row locks at checkout.
3. Buyer adds to cart → `POST /api/v1/orders/checkout/` runs in **one transaction**: it splits the cart **per store**, re-validates availability and price, reserves inventory, and captures the payment. Any failure rolls the whole checkout back — no order, no reservation, no charge. Sending an `idempotency_key` makes a retried checkout return the orders it already created instead of creating more.
4. Seller updates order status; refunds reverse the commission ledger.

> A cart line whose price changed since it was added is rejected with `400` + `code: "price_changed"`. `POST /api/v1/orders/cart/refresh-prices/` accepts the current catalogue prices (the checkout page shows a "Prices have changed" banner and calls it).

### Localisation (Algeria)
- **Three UI languages** — French (default), Arabic (RTL) and English — picked in the header and persisted in the `mh_locale` cookie. There is no `/<lang>/` URL segment yet (SEO routing is a later phase); the root layout reads the cookie server-side, so `<html lang dir>` and the message catalogue are right in the first byte and there is no flash. The API follows the same cookie through the `Accept-Language` header the client sends.
- **Emails and SMS** follow each user's `preferred_language` (profile field, default `fr`); API responses expose translated `*_label` twins of enum/status values, with the raw values unchanged in the contract.
- **Prices are DZD.** A user preference (`mh_price_display`) switches between `45 000 DZD` and the colloquial centime-millions habit (`1 million` = 10 000 DA).
- **Addresses are geography FKs** — a street line plus a `Wilaya` (69, matching the Nov 2025 official list) and an optional `Commune` (~1,540), served by read-only `/api/v1/geography/` endpoints and picked with a cascading wilaya → commune selector.

### Payments
Payments are **simulated** — there is no live payment gateway, and there is exactly **one** capture path: `process_simulated_payment()`, called from inside the checkout transaction. It writes a `Transaction` plus a `PlatformCommissionLedger` entry using `PLATFORM_COMMISSION_RATE`, and locks the order row so one order can never be charged twice — not concurrently, not by a client retry. `POST /api/v1/payments/simulate/` exists as the retry endpoint for an unpaid (`PENDING`) order and accepts an `idempotency_key` to replay a previous attempt safely.

---

## Known limitations

Tracked with concrete file references in [docs/todo.md](docs/todo.md):

- **1 known defect pinned by a strict xfail** in the backend suite — a review author can never edit their own review (fixed in Phase 17; see [docs/todo.md](docs/todo.md) §0.3).
- **Refunds never restock inventory** — `return_inventory_for_order()` exists but nothing calls it (Phase 18).
- **No Docker or deploy configuration** (Phases 19–20).

---

## Contributing to the roadmap

Phases in [docs/todo.md](docs/todo.md) are ordered by dependency:

| Wave | Phases |
|---|---|
| Strategy | 0 |
| Foundation | 1–5 |
| Correctness | 6–10 |
| Marketplace core | 11–16 |
| Differentiate | 17–22 |
| Polish & grow | 23–26 |
| Ship | 27–29 |

---

## License

Released under the [MIT License](LICENSE).
