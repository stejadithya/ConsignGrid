# TyreGrow — Architecture

## 1. Overview

Diagram: [`architecture.drawio`](architecture.drawio). Open it at https://app.diagrams.net (File → Open from → Device), or with the draw.io VS Code extension.

A **modular monolith**: one FastAPI backend, one Next.js frontend and one PostgreSQL database. It has no message brokers, microservices or paid services, and can be deployed to any low-cost host that runs a Python web process, a Node process (or static export) and managed Postgres.

```
Browser ──> Next.js (frontend, :3000) ──/api/* rewrite──> FastAPI (backend, :8000) ──> PostgreSQL
```

The frontend proxies `/api/*` to the backend, so the browser sees a single origin. That lets the session token live in an **httpOnly, SameSite=Strict cookie**. The API also accepts `Authorization: Bearer` for tests and integrations.

## 2. Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (sync ORM), Pydantic v2, Alembic | Sync SQLAlchemy keeps transaction and locking semantics simple and explicit. |
| DB | PostgreSQL 16 | Row locks (`FOR UPDATE`), check constraints, partial unique indexes. |
| Auth | Password (bcrypt) + signed JWT (PyJWT) | Stateless; short-lived tokens; role → permission map in code. |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS v4, lucide-react icons, Geist font | In-repo design system (`components/ui.tsx`, `components/flow.tsx`); no heavy UI kit. |
| Tests | pytest (backend, against a real Postgres), Vitest (frontend units), Playwright (e2e) | Inventory tests need real Postgres locking, so SQLite is not used. |
| Local dev | Docker Compose (Postgres) or a local Postgres; `.env` configuration | |

## 3. Backend layout

```
backend/
  app/
    main.py                 FastAPI app, router registration, error handlers
    core/                   config, db session, security (JWT/bcrypt), errors,
                            permissions (roles→permissions), numbering (document numbers)
    modules/
      identity/             users, login, current user, role checks, staff handover (handover.py)
      audit/                audit_events + record_audit()
      catalogue/            products, tax rates
      customers/            resellers, locations, agreements, customer prices
      inventory/            ledger, balances, reservations, reconciliation  ← core
      consignment/          allocations (targets) + change history
      purchasing/           purchase orders, goods receipts
      sales/                consignment sales + reversal
      replenishment/        requests (+backorders), allocations, deliveries
      transfers/            inter-reseller transfers
      stocktakes/           counts, classification, approval
      invoicing/            invoices, snapshots, accounting export boundary
      reporting/            dashboard + reports (read-only queries), incl. by dealer by SKU (dealer_sku.py)
      pilot/                pilot feedback + reference documents (dealer price list)
    assets/reference/       reference document files (served by the API, authenticated)
    models.py               imports all module models (for Alembic)
  alembic/                  migrations
  scripts/reset_to_pilot.py one-time clean pilot reset (explicit confirmation; never run on deploy)
  tests/
```

Each module contains `models.py` (SQLAlchemy), `schemas.py` (Pydantic), `service.py` (business logic) and `router.py` (HTTP).

**Module boundaries**
- Only `inventory.service` writes `stock_balances`, `inventory_transactions`, `inventory_entries` and `stock_reservations`. Other modules call its functions (`move`, `reserve`, `release`, `block`, `unblock`).
- Workflow modules own their documents and call the inventory, replenishment and audit services.
- `reporting` is read-only.
- Services never commit. The router commits once per request, so a whole business operation (for example sale + ledger + replenishment request + allocation) is atomic. Any exception rolls back everything.

## 4. Error model

Domain exceptions in `core/errors.py` map to HTTP responses:
`NotFoundError` → 404, `PermissionDeniedError` → 403, `BusinessRuleError` → 422, `ConflictError` (insufficient stock, wrong state, concurrent update, deadlock) → 409.
Response body: `{"detail": "...", "code": "..."}`.

## 5. Security
- Permissions are checked in routers via `require(permission)` dependencies, and **again in services** for data scoping (reseller users are filtered to their own `reseller_id`; any other id returns 404, so the existence of other records is not revealed).
- Passwords: bcrypt. The JWT secret comes from an environment variable; the app refuses to start in `production` with the default secret.
- No secrets in the repository. `.env.example` contains development placeholders only.
- There is no demo data or seed. `scripts/reset_to_pilot.py` (explicit `--confirm RESET-PILOT`, extra guard in production) is the only bulk data operation.
- Four business roles (Relationship Manager, Warehouse Manager, Sales Representative, Reseller); see `docs/PILOT_USERS.md`. Reseller users are scoped to their own reseller in every service: they may report their own sales (agreed price only) and request replenishment within their target.
- Set-up and administrator-chosen passwords must be changed at first sign-in (`users.must_change_password`).
- Reference documents (the dealer price list) are served by the authenticated API (`/api/reference-documents`), staff only, never from public static files.

## 6. Branding and design system
- Frontend: `frontend/src/config/branding.ts` (display name, descriptor, tagline, logo path and intrinsic size), overridable by `NEXT_PUBLIC_BRAND_*` env vars. Colours, typography, radii and shadows are design tokens in `frontend/src/app/globals.css`. See `docs/DESIGN_SYSTEM.md`.
- Backend: the `APP_DISPLAY_NAME` setting (used in the API title and on printable invoices).
- The product name does not appear in table names, API paths, domain entities or document number prefixes.

## 7. Configuration (env vars)
See `backend/.env.example`. Key business settings:
- `DEFAULT_CURRENCY`: currency code shown on invoices.
- `AUTO_ALLOCATE_ON_CREATE`: allocate warehouse stock immediately when replenishment demand is created.
- `ALLOCATION_POLICY`: `PRIORITY_THEN_OLDEST` (the only policy implemented; pluggable).
- `INVOICE_DUE_DAYS_DEFAULT`: fallback payment terms.
- `STOCKTAKE_FIND_DAYS` (1.11, default 5): days a dealer has to find tyres not found at a stock check before they are invoiced as sold. `STOCKTAKE_REMINDER_HOURS` (default 24) spaces the reminders.
- `CRON_SECRET`: protects the daily jobs (`/api/proofs/retention/cron`, `/api/stocktakes/auto-invoice/cron`).

## 8. Deployment (future — nothing deployed yet)
See `docs/DEPLOYMENT.md`. Target: one container for the backend (uvicorn), one for the frontend (`next start`), and managed Postgres. Migrations run with `alembic upgrade head` as a release step.
