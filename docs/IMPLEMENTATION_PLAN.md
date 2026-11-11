# TyreGrow — Implementation Plan

Status key: ✅ done and tested · 🟡 partial · ⏳ not started · ⏸ deferred (out of MVP scope)

## Phase 0 — Discovery ✅
- ✅ Business case read in full (8 pages). Copy stored at `docs/reference/`.
- ✅ Requirements, architecture, data model, inventory rules, decision log, deployment notes.

## Phase 1 — Foundation ✅
- ✅ Repository structure, config via environment, Alembic migrations (0001 foundation, 0002 workflows + invoicing), Docker Compose for Postgres.
- ✅ Authentication (bcrypt + JWT in an httpOnly SameSite=Strict cookie, or bearer), six roles, permission map enforced in the API.
- ✅ Reseller data scoping (out-of-scope records → 404; transfer counterparties redacted).
- ✅ Audit log for administrative, inventory and financial actions.
- ✅ Catalogue (structured tyre attributes, exact-SKU matching, cost visibility by permission), configurable tax rates.
- ✅ Resellers, consignment agreements (transfer-consent rule), multiple locations, warehouses, effective-dated customer prices.
- ✅ Consignment targets with change history; positions view (target, on hand, open demand, inbound, unmet).
- ✅ User administration.

## Phase 2 — Inventory core ✅
- ✅ Double-entry ledger with virtual locations; append-only; compensating reversals.
- ✅ On-hand / reserved / blocked buckets; DB constraints make negative availability impossible.
- ✅ Row-locked reservations; deterministic lock order; deadlocks surface as HTTP 409 "retry".
- ✅ Opening balances, approved adjustments, block/unblock, write-off.
- ✅ Reconciliation (rebuild from history) and conservation check (every transaction balances).

## Phase 3 — Business workflows ✅
- ✅ Purchase orders, goods receipts (accepted/damaged, with or without a PO), incoming quantities (never stock).
- ✅ Consignment sales (multi-line, price and tax snapshots, manual price with reason), reversal of uninvoiced lines.
- ✅ Replenishment: sale-triggered (capped by target), transfer obligations, target-shortfall generation, manual requests (override above shortfall); duplicate-demand prevention under lock.
- ✅ Allocation (auto on creation for active resellers; proposal + confirm after receipts, priority then oldest), release, priority/expected-date/PO linking with reasons, cancellation with permission and reason.
- ✅ Deliveries: dispatch → transit → receipt; short receipts; return / lost / late resolution.
- ✅ Inter-reseller transfers: exact-SKU source search, approval with consent rules, reservation, collection, receipt, discrepancy resolution, reversal after collection, cancellation before collection, linked source obligation, optional destination-backorder coverage.
- ✅ Stocktakes: full count, submission snapshot, mandatory sold/missing classification, approval posting sale / loss / gain / block.

## Phase 4 — Invoicing and reporting ✅
- ✅ Invoices from uninvoiced sale lines; full financial snapshots; draft → issued → void; duplicate prevention (row locks + partial unique index); printable invoice.
- ✅ Accounting export boundary (`invoice.v1` payload, pluggable exporter, external reference).
- ✅ Mandatory reports: total consignment stock, backorders (allocated vs awaiting supply, by reason), reseller transaction history (opening balance, running SKU balances, invoice and transfer links, outstanding obligations split by reason).
- ✅ Additional: warehouse availability, demand by SKU, sold-but-uninvoiced, stocktake discrepancies, consignment ageing, dashboard.

## Phase 5 — Frontend and hardening 🟡
- ✅ Next.js application covering every navigation module, with permission-filtered navigation and deferred modules marked "not yet available".
- ✅ Guided transfer wizard; pick & dispatch; allocation proposal; mobile-friendly stocktake count; printable invoice.
- ✅ Demo seed used during development — **removed for the pilot** (replaced by `scripts/reset_to_pilot.py`).
- ✅ Frontend component tests (Vitest) and Playwright e2e for the three scenarios and reseller isolation.
- ✅ Deployment documentation (`docs/DEPLOYMENT.md`); nothing deployed.
- 🟡 Usability review with real warehouse and sales staff: not yet done.
- ⏳ Login rate limiting (recommended at the proxy; see deployment notes).
- ⏳ Load and volume testing.

## Phase 6 — Business pilot preparation ✅
- ✅ Clean pilot state: all demo data and every mechanism that could recreate it removed; one-time guarded reset script and workflow.
- ✅ Four business roles with backend-enforced permissions and reseller isolation; reseller self-service (report sale, request replenishment).
- ✅ Role-specific dashboards and navigation; forced password change for set-up passwords; pilot feedback; dealer price list as an authenticated reference document.
- ✅ Product master import from Excel (standard template, check-then-import, RM/WM/Admin); July 2026 dealer price list loaded (38 SKUs, 1 obscured row rejected).
- ✅ Administrator super user with forced password change; `create_admin` safe on live data.

## Deferred (post-MVP) ⏸
Reseller self-service actions (report sales, acknowledge deliveries), notifications, credit notes and returns (invoiced-sale corrections), live accounting integration, DOT/batch tracking, multi-SKU transfer documents, forecasting and analytics (BC Phases 2–3).

## Test results (latest run)

| Suite | Command | Result |
|---|---|---|
| Backend (pytest, PostgreSQL 16) | `cd backend && pytest` | **60 passed** |
| Backend lint | `ruff check .` | clean |
| Migrations | `alembic upgrade head` / `downgrade base` / `alembic check` | round-trip OK, no drift |
| Frontend unit/component (Vitest) | `npm test` | **7 passed** |
| Frontend type check + lint | `npm run typecheck && npm run lint` | clean |
| Frontend production build | `npm run build` | OK (23 routes) |
| End-to-end (Playwright, Chromium) | `npm run test:e2e` | **4 passed** |

Acceptance tests from the master instructions §9 map to:
1 → `test_1_standard_sale_and_replenishment` · 2 → `test_2_warehouse_stockout_creates_backorder_until_delivered` ·
3 → `test_3_inter_reseller_transfer` · 4 → `test_4_partial_backorder_fulfilment` ·
5 → `test_concurrent_reservations_cannot_over_allocate`, `test_many_concurrent_small_reservations_never_exceed_stock`, `test_concurrent_invoicing_of_same_sale_line` ·
6 → `test_6_reseller_access_isolation`, `test_reseller_user_sees_only_own_balances`, `test_reseller_users_do_not_see_transfer_counterparty` ·
7 → `test_7a/7b/7c_*`, `test_delivery_short_receipt_and_resolution` ·
8 → `test_reconciliation_rebuilds_balances_from_history`.

## Known limitations and open issues
- Docker Compose is provided but was not executed in the build environment (no Docker daemon); tests ran against a local PostgreSQL 16 with the same settings.
- Invoiced sales cannot be corrected without voiding the invoice (credit notes deferred, A-010).
- Allocation defaults to the default warehouse. Multiple warehouses are modelled, but the UI has no warehouse chooser for allocation.
- Large reseller histories are returned in one response; add pagination if volumes grow.
- The business decisions in BC §16 are still open. Current behaviour follows the assumptions in `DECISION_LOG.md`.

## Milestone log
| Milestone | Scope | Tests at milestone |
|---|---|---|
| M1 | Phases 0–2 | 25 backend |
| M2 | Phase 3 workflows | 44 backend |
| M3 | Phase 4 invoicing and reporting | 55 backend |
| M4 | Frontend, seed, e2e | 58 backend · 7 unit · 4 e2e |
| M5 | Hardening (counterparty redaction, on-hold allocation), docs | 60 backend · 7 unit · 4 e2e |
| M7 | Pilot preparation: clean state, four roles, role dashboards, reset script, feedback, price list reference (`docs/PILOT_USERS.md`) | 107 backend · 7 unit · 4 e2e |
| M6 | UI/UX redesign: TyreGrow design system, new login, app shell, dashboard, product detail page, queue-style operational pages (`docs/DESIGN_SYSTEM.md`) | 7 unit · 4 e2e · axe 0 violations |
