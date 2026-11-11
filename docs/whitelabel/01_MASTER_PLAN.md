# ConsignGrid — White-label Master Plan

> **Working name:** ConsignGrid (from the repository name). It is a placeholder brand: every customer-facing name,
> logo, colour and word in this product is configuration, so the name can change per customer or for the whole
> product without code changes.
>
> **Starting point:** TyreGrow 1.11.0, a production-grade consignment platform built for one NZ tyre distributor
> (about 30 dealers). Owner: Seven Hills Global.
>
> **Goal:** one configurable, multi-industry, white-label consignment inventory product, sold worldwide through
> direct SaaS, white-label resellers and cloud marketplaces.

---

## 1. Where we start: an honest audit of TyreGrow

### What is already world-class (keep and protect)

| Asset | Why it matters commercially |
|---|---|
| **Double-entry inventory ledger** with virtual locations (supplier, transit, sold, scrap, adjustment) and a reconciliation endpoint | Auditors and finance teams trust it. Most SMB tools only store balances. This is the core moat. |
| **Reserved / blocked / available buckets**, DB constraints, row locks, concurrency tests | Stock cannot go negative or be double-allocated. Enterprise-grade. |
| **The full consignment loop:** sale → invoiceable → replenish to target → dispatch → receipt; backorders; inter-dealer transfers with source replacement obligation; stock checks with a "find window" before invoicing | This is the hard domain logic competitors don't have. Transfers with replacement obligation are rare. |
| **Invoice snapshots + duplicate-invoice prevention at DB level** + accounting export boundary | Clean hand-off to Xero/QuickBooks/Zoho/Tally. |
| **Role-based access, dealer data isolation (404 not 403), audit log, password policy, account lockout** | Passes security questionnaires. |
| **Partner stock API** (hashed keys) | Lets a supplier's website show live dealer/warehouse availability. A selling point. |
| **Branding already centralised** (`branding.ts`, `APP_DISPLAY_NAME`, design tokens) and no brand in table names, API paths or document prefixes | White-labelling is cheap. |
| ~400 backend tests on real Postgres, Vitest, Playwright, axe accessibility checks | Gives us room to change things safely. |

### What ties it to tyres, NZ and one customer (must change)

| Coupling | Where | Effort |
|---|---|---|
| Product = tyre: `width`, `aspect_ratio`, `rim_diameter`, `load_index`, `speed_rating` are **required** columns with a check constraint | `catalogue/models.py`, importer, product form, search, partner API, reports (15 files, ~90 references) | **L** |
| Wording "tyre(s)" and "Dealer" hard-coded on screens, PDFs, emails and notifications | ~180 files | **M** (mechanical, but large) |
| One currency, one tax rate per sale line, tax-exclusive prices, `Pacific/Auckland`, GST wording | config, invoicing, format.ts | **M** |
| Xero as the only named accounting system | invoicing, finance screens | **S** |
| Single-tenant: one database = one customer; `sku`, `account_ref`, location codes are globally unique | every table | **XL** (see §3) |
| English only, strings inline in components | frontend | **L** |
| Customer artefacts (price list, business case, UAT PDFs, names in docs) | repo | **Done** in the baseline commit |
| Integer quantities only (no units of measure) | ledger | **L** (needed for tiles, agri, building materials) |
| No lot / serial / expiry tracking | ledger and documents | **L** (needed for medical, agri, batteries, tiles) |

---

## 2. Product principles (the rules every change follows)

1. **The ledger is sacred.** All stock still moves through `inventory.service` (move / reserve / release / block). New
   dimensions (lot, serial, UoM) are added *around* it, with the reconciliation check kept green.
2. **Configuration, not forks.** One codebase. A customer differs only by its **Brand Pack** (name, logo, colours,
   domain, emails, legal entity), its **Industry Pack** (item attributes, words, rules, templates) and its
   **Policy settings** (billing trigger, approvals, tax, currency). We never branch the code per customer.
3. **Today's behaviour is the default.** With the `tyres` industry pack the product behaves exactly like TyreGrow 1.11,
   so the reference customer and the test suite keep working while we generalise.
4. **Additive migrations and APIs** (the existing TyreGrow rules 7 and 8 stay in force).
5. **Every customer-visible word is a term**, e.g. `{item}`, `{partner}`, `{site}`, so "Dealer / tyre / shop" can
   become "Hospital / implant / theatre" or "Store / SKU / outlet".
6. **Self-serve first.** Anything a customer needs on day one (branding, terms, catalogue, partners, opening stock)
   must be doable in a setup wizard or by CSV, without our engineers.

---

## 3. Target architecture

### 3.1 Configuration layers

```
┌──────────────────────────────────────────────────────────────┐
│ Brand Pack        name, logo, colours, favicon, domain,       │  per customer (or per reseller)
│                   email sender, legal entity, support links   │
├──────────────────────────────────────────────────────────────┤
│ Industry Pack     item attribute schema, item label format,   │  chosen from a library:
│                   vocabulary (item/partner/site), tracking    │  tyres, auto-parts, medical,
│                   mode (none/lot/serial/expiry), import       │  industrial, agri, fmcg,
│                   template, default rules                     │  building, furniture, generic
├──────────────────────────────────────────────────────────────┤
│ Policy            billing trigger (on sale / on use /         │  per customer, some per
│                   periodic / on stock check), approvals,      │  agreement (partner)
│                   ownership, transfer consent, find window,   │
│                   currency, tax regime, locale, time zone     │
├──────────────────────────────────────────────────────────────┤
│ Core platform     ledger, workflows, roles, audit, API        │  identical for everybody
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Tenancy: two stages (recommended)

| Stage | Model | Who it serves | Why |
|---|---|---|---|
| **A. Now → month 4** | **Silo**: one deployment (app + database) per customer, stamped out from the same image with its Brand + Industry Pack | Reference customer, pilots, white-label resellers, enterprise and medical buyers who demand data isolation, AWS/Azure "private offer" deals | Zero risk to the ledger, no re-keying of unique constraints, sell immediately. Infra cost ~US$25–60/month per customer on managed Postgres + containers, fine at Growth/Enterprise prices. |
| **B. Month 4 → 9** | **Pool**: shared deployment, `tenant_id` on every table, Postgres **Row-Level Security**, tenant resolved from sub-domain | Starter tier, marketplace self-serve sign-ups, AppSumo | Needed for US$99/month economics. Every unique constraint (SKU, account ref, location code, document numbers) becomes `(tenant_id, …)`. Big but mechanical once the code is generic. |

Both stages run the **same code**: in silo mode there is exactly one tenant. We design for B while shipping A.

### 3.3 Generic items (the core generalisation)

- `products` gains `attributes JSONB` and `item_type`; the tyre columns become **nullable** (the tyre pack still
  requires them through validation, so behaviour is unchanged for tyres).
- `item_attribute_definitions` (per pack / tenant): key, label, type (text, number, enum, date, boolean), unit,
  required, searchable, shown-in-label, order. Drives the product form, import template, search filters and the
  partner API automatically.
- **Item label template** per pack, e.g. tyres `{brand} {pattern} {width}/{aspect_ratio}R{rim} {load_index}{speed}`,
  medical `{brand} {model} {size} REF {ref}`.
- **Tracking mode** per item: `NONE | LOT | SERIAL | LOT_EXPIRY`. Adds `stock_lots` (lot number, expiry, manufacture
  date) and an optional `lot_id` on ledger entries; FEFO (first-expiry-first-out) allocation policy; recall lookup.
- **Units of measure** (later phase): base unit + pack conversions (box ↔ m² for tiles, case ↔ each for FMCG).

### 3.4 Billing triggers (the "configurable rules" in the strategy)

| Trigger | Industries | Status |
|---|---|---|
| On reported sale | tyres, auto parts, furniture, retail | ✅ exists |
| On stock check (not found = sold after find window) | all | ✅ exists |
| **On use / consumption** (bill-only, bill & replace) with case/job reference | medical devices, industrial MRO | new: a "usage" document = sale with a different source and required reference fields |
| **Periodic statement** (monthly roll-up of usage) | MRO, agri, FMCG scan-based trading | new: scheduled invoice run per agreement |
| On expiry or age limit (buy-back or charge) | medical, agri, tyres (DOT age) | new, later |

### 3.5 Global readiness

- Currency per tenant **and** per partner agreement; money stays decimal strings (D-015).
- Tax engine: a tax *profile* per partner with one or more components (NZ/AU GST, UK/EU VAT incl. reverse charge,
  India CGST+SGST / IGST with HSN codes, US sales tax via an Avalara/TaxJar adapter later). Tax-inclusive or
  -exclusive price lists.
- i18n: extract strings to message catalogues (`next-intl`-style), start with en-NZ/en-AU/en-GB/en-US/en-IN, then
  ar (RTL) and others; locale-aware number/date/currency formatting.
- Privacy and residency: region-pinned silo deployments (ANZ, India, EU, ME, US), GDPR/NZ Privacy Act/AU APPs/India
  DPDP data-processing terms, data export and delete per tenant.
- Accounting adapters behind the existing `AccountingExporter`: Xero (ANZ/UK), MYOB (AU), QuickBooks (US/UK/AU),
  Zoho Books + Tally (India), Sage (UK/ZA), NetSuite / Odoo (mid-market).

---

## 4. Roadmap (phases, each shippable)

Effort: S < 3 days, M ≈ 1 week, L ≈ 2–3 weeks, XL > 1 month (one experienced engineer).

### Phase 0 — Clean handover (✅ done in this branch)
- Import 1.11.0, remove the previous customer's price list, business case and UAT PDFs; reference documents become
  per-deployment; fictional sample catalogue. All tests green.
- **Open: confirm licence/IP position in writing** (see §6).

### Phase 1 — White-label foundation (silo-ready) · *weeks 1–4*
| Step | What | Size |
|---|---|---|
| 1.1 | **Brand Pack**: neutral default brand, logo, accent colour, legal entity, support contact, email sender — all from one config (env + `brand.json`), backend and frontend; remove "TyreGrow" from code paths | S |
| 1.2 | **Vocabulary / terminology layer**: `terms` from the Industry Pack (item, items, partner, site, rep…) used by screens, PDFs, emails and notifications | M |
| 1.3 | **Industry Pack registry** (`tyres`, `generic` first) + `GET /api/config` so the UI reads brand, terms and attribute schema at run time | S |
| 1.4 | **Generic item attributes**: `attributes JSONB`, nullable tyre columns, attribute definitions, label template; product form, import template, search and partner API driven by the schema | L |
| 1.5 | Rename user-facing "Xero" to "accounting system" (Xero stays as one adapter) | S |
| 1.6 | **Deployment kit**: Dockerfiles, `docker-compose.prod.yml`, one-command "new customer" script (brand + pack + admin user), health checks | M |

### Phase 2 — Sellable to the first non-tyre industries · *weeks 5–10*
| 2.1 | Lot / serial / expiry tracking + FEFO + recall search (unlocks medical, agri, batteries) | L |
| 2.2 | Billing on use (bill-only / bill & replace with case reference) + periodic statements | M |
| 2.3 | Multi-currency + tax profiles (GST, VAT, India GST components) | M |
| 2.4 | **Setup wizard** + CSV import for partners, sites, targets and opening stock | M |
| 2.5 | i18n extraction (English variants first) | L |
| 2.6 | Accounting adapters: Xero live API, QuickBooks Online, Zoho Books | M each |
| 2.7 | Industry packs: auto-parts & batteries, medical devices, industrial spares | S each once 1.4/2.1 exist |

### Phase 3 — Pooled SaaS + marketplaces · *months 3–6*
| 3.1 | Pooled multi-tenancy: `tenant_id` + RLS + tenant-scoped uniques + sub-domain routing | XL |
| 3.2 | Self-serve sign-up, trials, plans and limits (locations, users), Stripe billing | M |
| 3.3 | AWS Marketplace SaaS integration (ResolveCustomer, entitlements/metering, SNS events), then Azure and GCP | M each |
| 3.4 | SSO (SAML/OIDC), SCIM, custom roles (D-009 revisited) | M |
| 3.5 | Reseller (white-label partner) console: create tenants, brand them, see usage for revenue share | M |
| 3.6 | Security pack: pen test, SOC 2 Type I readiness, DPA templates, status page, backups/DR runbook | M |

### Phase 4 — Depth and scale · *months 6–12*
Units of measure, mobile barcode/GS1 scanning (UDI DI/PI parsing), offline stock checks, POS/e-commerce feeds
(Shopify, scan-based trading), forecasting and min/max suggestions, Arabic (RTL), EU data region, Odoo/NetSuite apps.

---

## 5. First 90 days (aligned to the strategy document)

| Days | Product | Commercial |
|---|---|---|
| **1–15** | Phase 0 ✅, Phase 1.1–1.3 (brand, vocabulary, pack registry). Demo tenant with a fictional brand. | Confirm licence/IP terms; choose final product name and buy domains; register trademarks in NZ/AU (and Madrid filing later). |
| **15–45** | Phase 1.4–1.6 (generic items, deployment kit) + 2.4 setup wizard. Record a 3-minute demo per vertical (tyres, auto parts, medical). | Website + pricing page; G2 / Capterra / GetApp / SoftwareSuggest profiles; LinkedIn outreach list of 300 distributors in ANZ. |
| **45–75** | Phase 2.1–2.3 (lots/expiry, billing on use, tax/currency) for pilot needs. | Sign 3–5 discounted pilots (target: 1 auto parts, 1 medical distributor, 1 building materials/tiles). Recruit 2 white-label partners (ANZ IT consultancies, an India Zoho/Tally partner). |
| **75–90** | Fix pilot feedback; AWS Marketplace limited listing (silo deployments as private offers first). | Case study from the reference customer; first paid conversions; marketplace listing in "Limited" state. |

---

## 6. Decisions and assumptions (please confirm or correct)

| # | Assumption I am working with | Why it matters |
|---|---|---|
| W-001 | **Seven Hills Global owns the IP** in TyreGrow and may resell it; the reference customer has a licence, not ownership, and has no exclusivity in tyres. | Without this, we cannot sell to other tyre distributors. Get it in writing. |
| W-002 | **ConsignGrid** is a working product name only. | Every name is config; no rework if it changes. |
| W-003 | **Silo first, pooled later** (§3.2). | Determines the next 4 months of engineering. |
| W-004 | **Tyres stays the default industry pack** until the generic product is proven, so the reference customer's behaviour never changes. | Protects the reference customer. |
| W-005 | We keep the current stack (FastAPI + Postgres + Next.js); hosting moves from Vercel to containers (AWS/Azure) for marketplaces and data residency. | Marketplace listings and regional data rules favour container deployments. |
| W-006 | English (NZ/AU/UK/US/IN variants) first; RTL Arabic later for the Middle East. | Effort for i18n. |
| W-007 | The previous customer's confidential material is excluded from this repository; their history stays in their own repository. | Clean handover. |

See [`02_INDUSTRY_ANALYSIS.md`](02_INDUSTRY_ANALYSIS.md) for vertical-by-vertical requirements,
[`03_GO_TO_MARKET.md`](03_GO_TO_MARKET.md) for channels, pricing and marketplaces,
[`04_CUSTOMER_PLAYBOOK.md`](04_CUSTOMER_PLAYBOOK.md) for how to brand and configure a new customer, and
[`PROGRESS.md`](PROGRESS.md) for the step-by-step log.
