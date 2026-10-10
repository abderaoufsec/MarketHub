# MarketHub

An open-source marketplace platform — multi-vendor stores, product catalog, cart & checkout, inventory tracking, reviews, wishlist, and simulated payments.

**Stack:** Django REST Framework · PostgreSQL · Next.js 14 (App Router) · Tailwind CSS

---

## Status

MarketHub is **under active development**. The core commerce flows work end-to-end, but the project is not yet production-ready.

| Area | State |
|---|---|
| Backend | 6 apps · 51 API routes · migrations in sync |
| Frontend | 19 pages (Next.js App Router) |
| Tests | Backend: **158 passing** (11 strict xfails pinning known defects) · Frontend: **45 unit + 5 e2e passing** |
| CI | **GitHub Actions** — backend, frontend and security-audit jobs on every push/PR |
| API docs | ⚠️ Not yet generated — Phase 9 |

The full 29-phase plan to close these gaps lives in **[docs/todo.md](docs/todo.md)**.

---

## Repository layout

```
MarketHub/
├── backend/                 # Django project
│   ├── core/                # settings, root urls, wsgi/asgi
│   ├── apps/
│   │   ├── users/           # auth, profiles, addresses
│   │   ├── stores/          # seller stores & followers
│   │   ├── products/        # catalog, reviews, wishlist
│   │   ├── inventory/       # stock levels & audit log
│   │   ├── orders/          # cart, checkout, order lifecycle
│   │   └── payments/        # transactions, refunds, commissions
│   ├── static/              # source static assets
│   ├── templates/           # Django templates
│   ├── manage.py
│   └── requirements.txt
├── frontend/                # Next.js 14 app
│   └── src/
│       ├── app/             # App Router pages
│       ├── components/      # common / product components
│       ├── context/         # AuthContext
│       └── lib/             # axios client + API services
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
| `/api/auth/` | users — register, login, logout, profile, addresses |
| `/api/stores/` | stores — public store list/detail, seller store management |
| `/api/products/` | products — catalog, reviews, wishlist |
| `/api/inventory/` | inventory — stock, low-stock, audit log |
| `/api/orders/` | orders — cart, checkout, order history |
| `/api/payments/` | payments — transactions, refunds, commissions |

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
NEXT_PUBLIC_API_URL=http://localhost:8000/api
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

> The backend suite pins 11 known defects as `xfail(strict=True)` (see [docs/todo.md](docs/todo.md) §0.3): they are expected to fail until Phase 6 fixes them, and the suite turns red the moment a fix lands so the marker gets removed.

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
- Role-based access: buyers and sellers share one `User` model with an `is_seller` flag.
- Email verification tokens on registration.

> ⚠️ The frontend currently stores JWTs in JS-readable cookies, not `HttpOnly` cookies. Hardening is tracked in Phase 7 of the roadmap.

### Commerce flow
1. Seller creates a store, then products.
2. `Inventory` rows track stock per product/variant, with an `InventoryAuditLog` trail.
3. Buyer adds to cart → `POST /api/orders/checkout/` splits the cart **per store**, reserves inventory, and processes a simulated payment.
4. Seller updates order status; refunds reverse the commission ledger.

### Payments
Payments are **simulated** — there is no live payment gateway. `POST /api/payments/simulate/` always succeeds and writes a `Transaction` plus a `PlatformCommissionLedger` entry using `PLATFORM_COMMISSION_RATE`.

---

## Known limitations

Tracked with concrete file references in [docs/todo.md](docs/todo.md):

- **11 known defects pinned by strict xfails** in the backend suite — fixed in Phases 6–8, 17 (see [docs/todo.md](docs/todo.md) §0.3).
- **Transactional bugs in checkout** — `return` inside `transaction.atomic()` can commit partial state (Phase 6).
- **Inventory oversell race** — no `select_for_update()` / `F()` expressions (Phase 6).
- **`is_seller` is writable** via profile `PUT`, allowing privilege escalation (Phase 7).
- **Duplicate email-verification flows**, and no frontend verification page (Phase 8).
- **Product card images don't render** — serializer/field mismatch (Phase 12).
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
