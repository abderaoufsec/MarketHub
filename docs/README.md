# MarketHub Documentation

Everything beyond the code lives here.

## Contents

| Document | Description |
|---|---|
| [`product.md`](product.md) | **Product document** — positioning, personas, launch scope, adopted decisions, legal notes. *(Phase 0)* |
| [`todo.md`](todo.md) | **The 29-phase roadmap** — current status, per-phase tasks, acceptance criteria, and suggested sequencing. |

## Reading order

Start with [`product.md`](product.md) to understand *what* is being built and *why*, then
[`todo.md`](todo.md) for *how* and *when*. The roadmap opens with a **strategy section** (§0) and a
gap analysis recording the state of the project:

- competitor positioning and what is verified vs. assumed
- gaps found in the code, each mapped to the phase that fixes it
- north-star metrics and the MVP cut-line

Then the 29 phases, grouped into waves:

| Wave | Phases | Focus |
|---|---|---|
| **Strategy** | 0 | Validate what we're building against the real competitor |
| **Foundation** | 1–5 | Repo hygiene, config management, tests, lint, CI |
| **Correctness** | 6–10 | Transactions, security, identity (phone OTP), API contract, performance |
| **Marketplace core** | 11–16 | Locale, categories, listings, media, search, contact (Ouedkniss parity) |
| **Differentiate** | 17–22 | Trust, orders, payments, delivery, monetization, notifications |
| **Polish & grow** | 23–26 | PWA/performance, accessibility, dashboards, SEO |
| **Ship** | 27–29 | Packaging, deployment/compliance, launch |

Each phase carries concrete tasks and a **"Done when"** acceptance criterion.

## Planned additions

These documents are scheduled as their phases land:

- `api.md` — API reference and error-code catalogue *(Phase 9)*
- `architecture.md` — system design and data flow *(Phase 27)*
- `deployment.md` — hosting, environment variables, and release process *(Phase 27)*
- `moderation-playbook.md` — trust & safety operations *(Phase 27)*
- `CHANGELOG.md` — release notes *(Phase 27)*
