# MarketHub — Product Document

> **Phase 0 deliverable — 2026-10-10.** This is the single source of truth for *what* MarketHub is,
> *who* it is for, and *what we deliberately do not build*. Every roadmap phase in [`todo.md`](todo.md)
> should be traceable back to a decision recorded here.

---

## 1. Positioning

> **"Ouedkniss's reach, but you can trust the seller, pay safely, and get it delivered."**

MarketHub is an **Algerian classifieds + stores platform**. Anyone can post an ad in under
90 seconds and be contacted by phone/WhatsApp; businesses get a full store with inventory,
checkout and delivery. The product is won or lost on **trust, search quality, and posting speed** —
not on how many features the cart has.

### 1.1 Competitive baseline (verification status)

The roadmap's competitor claims were checked as far as remote access allowed on 2026-10-10.

| Claim (from `todo.md` §0.1) | Status | Evidence |
|---|---|---|
| Ouedkniss is an Algerian **classifieds** site (petites annonces), founded 2006, free ad posting | ✅ **Verified** | fr.wikipedia.org/wiki/Ouedkniss — "site web de petites annonces basé en Algérie", founded 2006 by five lycée students, "premier site de petites annonces gratuites en Algérie"; subsidiary **Autobip** (automotive) |
| One of the most visited sites in Algeria | ✅ **Verified** | Same article, citing *Le Soir d'Algérie* ("En Algérie, Ouedkniss est plus visité que Facebook") |
| Transactions are contact-first → meet/phone → cash | 🟡 **High confidence, not re-audited** | Consistent with the classifieds model above; **needs a live 2-hour session** (Phase 0 task) |
| Trust is weak: scams, fake and duplicate ads | 🟡 **Assumed** | Not verifiable remotely — requires reading recent app-store reviews / Facebook groups |
| Search = keyword + category + wilaya | 🟡 **Assumed** | Site is a JS app; could not be scraped for filter inventory |
| Arabic/French only, heavy pages, seller-arranged delivery | 🟡 **Assumed** | Needs Lighthouse + manual check on a mid-range Android |

**What this means:** the *direction* of the plan is verified (classifieds-first market, contact-driven,
free posting). The *gap analysis* cells above marked 🟡 must be confirmed by a real user/seller
session before the differentiation phases (17–21) are prioritised. This is the one Phase 0 task that
cannot be done from a terminal.

### 1.2 Where we win

| Axis | Ouedkniss | MarketHub |
|---|---|---|
| Trust | Common complaints: scams, duplicates | Verified phone, seller tiers, report/moderation SLA, duplicate-image detection, scam-pattern blocking |
| Payment | Mostly cash on meeting | Contact **and** optional checkout: COD first, CIB/Edahabia later |
| Delivery | Seller-arranged | Integrated Algerian carriers + tracking |
| Search | Keyword + category + wilaya | Per-category facets, typo-tolerant Arabic/French, saved searches + alerts |
| Speed/mobile | Heavy pages | PWA, image CDN, SSR, < 2 s LCP on mid-range Android over 4G |

---

## 2. Personas

### 2.1 Buyer — *Yacine, 27, Blida*
- Buys used phones and car parts; browses on a cheap Android over a metered connection.
- Primary action is **calling or WhatsApp-ing the seller**, not checking out.
- Has been burned (or nearly burned) by a fake ad before → needs visible proof the seller is real.
- Needs: search by wilaya + category + a few attributes, price in DA, photos that load fast,
  one-tap call/WhatsApp, and a way to report a scam in two taps.

### 2.2 Individual seller — *Amina, 34, Algiers*
- Sells occasional household items, a used phone, maybe a car. Posts a handful of ads a year.
- Will abandon anything slower than **90 seconds on a phone**.
- Wants: photo upload that works on a weak network, a phone-number field that gets her contacts,
  renewal before the ad expires, and freedom from scams/harassment.
- **Cannot be blocked by a 20-product cap** — today's `MAX_PRODUCTS_PER_SELLER = 20` is a
  store-era artefact (replaced by per-tier quotas in Phases 13/21).

### 2.3 Store owner — *Samir, phone shop, Blida*
- Runs a real inventory; wants a catalogue, stock control, and optional online payment/delivery.
- Will pay for **boosts, analytics, and bulk import** — not for the right to be listed.
- Wants: CSV import, order management, commission transparency, a verified-store badge.

**Design rule:** the buyer and individual seller flows are the *default* experience; store features
are an add-on. Any feature that slows down "post an ad" or "call the seller" is a regression.

---

## 3. Launch scope (MVP cut-line)

| Dimension | Choice | Rationale |
|---|---|---|
| Region | **1 wilaya — Blida** (fallback: Algiers) | Cold start is solved supply-first in one place (Phase 29) |
| Categories | **Phones & tablets · Cars · Electronics** | Highest ad density in Algerian classifieds; seed sellers are reachable in person |
| Languages | French + Arabic first, English third | Arabic RTL is a differentiator, French is the business lingua franca |
| Transaction | Contact-first + **COD** checkout for store products | Matches the habit; no payment-gateway dependency to launch |
| Cut-line | Phases 1–8, 11–16, 17 (basic), 22 (basic), 26 (basic SEO), 27, 28 | Everything else (online payments, delivery APIs, subscriptions, native apps) ships **after** launch |

**Non-goals (explicitly out of scope until after launch):**
- ❌ Online card payments (CIB/Edahabia) — no integration until the merchant/legal path is confirmed.
- ❌ Nationwide delivery integration — 1 wilaya is hand-delivered/relay-point at first.
- ❌ Native iOS/Android apps — the PWA is the mobile strategy.
- ❌ Subscription-only monetization — posting and contacting stay **free forever**.
- ❌ Subscriptions for buyers, auctions, B2B wholesale, social feed, AI features.
- ❌ Scraping or importing content from Ouedkniss or any competitor — seed supply is recruited
  personally and sellers import **their own** catalogues (Phase 29).

---

## 4. Decisions (roadmap §"Decisions needed from you")

Adopted on 2026-10-10 using the roadmap's recommendations. Any can be revisited — changing one
later requires an ADR (Phase 27).

| # | Decision | **Adopted answer** | Consequence |
|---|---|---|---|
| 1 | Product model | **Hybrid** — classifieds posting for everyone + store features/checkout for businesses | Phase 13 evolves `Product` → `Listing`; Phases 11–16 are the critical path |
| 2 | Catalogue model | **Evolve `Product` into `Listing`** with a nullable `store` | One search index, no parallel catalogues |
| 3 | Search engine | **Postgres FTS + `pg_trgm`** behind a `SearchService` interface | No extra infra at launch; Meilisearch/Typesense can be swapped in |
| 4 | JWT storage | **Bearer tokens in JS-readable cookies for now** → HttpOnly cookie + CSRF for web, bearer for mobile | Truthful README today (Phase 2/7), cookie auth implemented in Phase 7 |
| 5 | Online payments | **Launch COD only**; aggregator after legal confirmation | Phase 19 builds the `PaymentProvider` interface first |
| 6 | Real-time chat | **Polling + push for MVP**; Channels/WebSockets in v1.1 | Phase 16 ships without a socket server |
| 7 | Launch region & categories | **Blida × (phones, cars, electronics)** | Written into §3 above; changeable without re-planning |
| 8 | Hosting region | **Decide after measuring latency from Algérie Télécom / Djezzy / Mobilis / Ooredoo** | Deferred to Phase 28; EU (Paris/Marseille) + CDN is the default hypothesis |

---

## 5. Legal & compliance notes (not legal advice)

To be confirmed with an Algerian lawyer before taking payments (tracked in Phase 28):

| Topic | Framework | What it means for MarketHub |
|---|---|---|
| Personal data | **Law 18-07** (protection des données à caractère personnel, 2018) + the CNPDP | Privacy policy in ar/fr, consent, retention schedule, data export/deletion, careful with phone numbers and ID photos used for verification |
| E-commerce | **Law 18-05** (commerce électronique, 2018) | Required disclosures for distance selling; terms of use; electronic contracting rules |
| Taking payments | Merchant agreement (SATIM / aggregator) + company registration | **Blocks Phase 19 online payments** — this is why COD launches first |
| Prohibited items | Platform policy + import/customs rules | Banned-items list enforced in Phase 17 pre-publish checks |
| Identity/verification | ID-photo + selfie review (Phase 17) | High-sensitivity personal data — needs explicit consent, restricted access, deletion policy |

---

## 6. North-star metrics (instrument in Phase 25)

| Metric | Target | Why |
|---|---|---|
| Time to post a listing (mobile) | < 90 s p75 | Posting friction is how classifieds win |
| Listings with ≥ 1 contact in 7 days | Growing weekly | Liquidity |
| % of listings flagged scam/duplicate | < 2 % | Trust |
| Search → contact conversion | Improving | Search quality |
| p75 LCP on 4G Android | < 2.5 s | Speed advantage |
| Seller 30-day retention | > 40 % | Supply-side health |

---

## 7. Open Phase 0 tasks (manual, cannot be automated)

- [ ] 2-hour live session on Ouedkniss as **buyer and seller** (web + Android) → replace the 🟡
      cells in §1.1 with observed facts (posting steps, contact options, promo pricing).
- [ ] Read 30–50 recent public complaints (Play Store / App Store reviews, Facebook groups) →
      rank the top 5 pains; feed into the marketing and priority list.
- [ ] Lawyer review of §5 (Law 18-07, Law 18-05, payment-taking entity requirements).
- [ ] Confirm seed sellers in Blida for the three launch categories (Phase 29 supply seeding).
