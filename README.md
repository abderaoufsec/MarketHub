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
| Tests | ⚠️ None yet — see [docs/todo.md](docs/todo.md) Phases 3–4 |
| CI | ⚠️ Not yet configured — Phase 5 |
| API docs | ⚠️ Not yet generated — Phase 9 |

The full 20-phase plan to close these gaps lives in **[docs/todo.md](docs/todo.md)**.

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

# Backend — tests (none exist yet; expect "NO TESTS RAN")
python manage.py test

# Frontend
cd ../frontend && npm run lint   # not yet configured; see Phase 4
```

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

- **No automated tests** for either backend or frontend.
- **Transactional bugs in checkout** — `return` inside `transaction.atomic()` can commit partial state (Phase 6).
- **Inventory oversell race** — no `select_for_update()` / `F()` expressions (Phase 6).
- **`is_seller` is writable** via profile `PUT`, allowing privilege escalation (Phase 7).
- **Duplicate email-verification flows**, and no frontend verification page (Phase 8).
- **Product card images don't render** — serializer/field mismatch (Phase 12).
- **No Docker, CI, or deploy configuration** (Phases 5 and 19–20).

---

## Contribing to the roadmap

Phases in [docs/todo.md](docs/todo.md) are ordered by dependency:

| Wave | Phases |
|---|---|
| Foundation | 1–5 |
| Correctness | 6–10 |
| Capability | 11–15 |
| Polish | 16–18 |
| Ship | 19–20 |

---

## License

Released under the [MIT License](LICENSE).
