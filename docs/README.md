# MarketHub Documentation

Everything beyond the code lives here.

## Contents

| Document | Description |
|---|---|
| [`todo.md`](todo.md) | **The 20-phase roadmap** — current status, per-phase tasks, acceptance criteria, and suggested sequencing. |

## Reading order

Start with [`todo.md`](todo.md). It opens with a **baseline audit** recording the state of the
project at the start of the roadmap:

- test runs and their results
- code size per project
- verified critical defects, each with file and line references

Then the 20 phases, grouped into five waves:

| Wave | Phases | Focus |
|---|---|---|
| **Foundation** | 1–5 | Repo hygiene, config management, tests, lint, CI |
| **Correctness** | 6–10 | Transactions, security, onboarding, API contract, performance |
| **Capability** | 11–15 | Real analytics, media, search, commerce rules, notifications |
| **Polish** | 16–18 | Rendering, accessibility, admin tooling |
| **Ship** | 19–20 | Packaging, documentation, deployment, observability |

Each phase carries concrete tasks and a **"Done when"** acceptance criterion.

## Planned additions

These documents are scheduled as their phases land:

- `api.md` — API reference and error-code catalogue *(Phase 9)*
- `architecture.md` — system design and data flow *(Phase 19)*
- `deployment.md` — hosting, environment variables, and release process *(Phase 19)*
