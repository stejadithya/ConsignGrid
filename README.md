# ConsignGrid

White-label B2B consignment inventory platform: a supplier keeps ownership of stock held at dealers, hospitals,
stores or job sites, invoices only what is sold, used or missing, replenishes partners to agreed targets, and moves
stock between partners. Configurable per customer (brand, industry vocabulary, item attributes, rules) from one
codebase.

> **ConsignGrid is a working name.** Every customer-visible name, logo, colour and word is configuration — see the
> [customer playbook](docs/whitelabel/04_CUSTOMER_PLAYBOOK.md). Plan and progress: [`docs/whitelabel/`](docs/whitelabel)
> ([master plan](docs/whitelabel/01_MASTER_PLAN.md) · [industry analysis](docs/whitelabel/02_INDUSTRY_ANALYSIS.md) ·
> [go-to-market](docs/whitelabel/03_GO_TO_MARKET.md) · [progress](docs/whitelabel/PROGRESS.md)).
>
> Built from TyreGrow 1.11.0 (a tyre distributor supplying 30+ dealers in New Zealand). The tyre industry pack is
> still the default, so the platform behaves exactly like that release until another pack is chosen.

## What is in the box

| Area | Status |
|---|---|
| Catalogue, resellers, locations, agreements, customer prices, targets | ✅ |
| Double-entry inventory ledger (on hand / reserved / blocked, transit, reconciliation) | ✅ |
| Scenario 1: sale → invoiceable → replenishment → dispatch → receipt | ✅ |
| Scenario 2: stockout → backorder → PO → receipt → proposed allocation → delivery | ✅ |
| Scenario 3: inter-reseller transfer with approval, consent, transit, discrepancy handling and source obligation | ✅ |
| Stocktakes with mandatory shortage classification | ✅ |
| Invoicing with snapshots, duplicate prevention and an accounting export boundary | ✅ |
| Mandatory reports: consignment stock, backorders, reseller transaction history (+ extra views, dashboard) | ✅ |
| Role-based access (6 roles), reseller data isolation, audit log | ✅ |
| Reseller self-service actions, notifications, credit notes, forecasting | ⏸ deferred (see `docs/IMPLEMENTATION_PLAN.md`) |

**Deploying to Vercel for testing:** follow [`docs/DEPLOY_VERCEL.md`](docs/DEPLOY_VERCEL.md).

Documentation lives in [`docs/`](docs): requirements, architecture, data model, **inventory rules**, implementation plan, decision log and deployment notes. The business case is in `docs/reference/`.

## Repository layout

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (Python 3.11+)
frontend/   Next.js + React + TypeScript + Tailwind CSS
docs/       Product and technical documentation
docker-compose.yml   Local PostgreSQL (dev + test databases)
```

## Running locally

Prerequisites: Python 3.11+, Node 20+ (22 recommended), and PostgreSQL 16 (via Docker Compose or a local install).

### 1. Database

```bash
docker compose up -d db          # creates databases "tyreworld" and "tyreworld_test" (user/password tyreworld)
```

Without Docker, create them yourself:

```sql
CREATE USER tyreworld WITH PASSWORD 'tyreworld';
CREATE DATABASE tyreworld OWNER tyreworld;
CREATE DATABASE tyreworld_test OWNER tyreworld;
```

### 2. Backend API (http://localhost:8000, docs at `/api/docs`)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                        # development defaults; never commit real secrets
alembic upgrade head                        # schema + system locations
# Create the pilot accounts on an empty database (DESTRUCTIVE; see docs/PILOT_USERS.md):
PILOT_RM_EMAIL=rm@example.com PILOT_WM_EMAIL=wm@example.com PILOT_SR_EMAIL=sr@example.com \
  python -m scripts.reset_to_pilot --confirm RESET-PILOT   # prints one-time temporary passwords
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev                                  # proxies /api/* to http://localhost:8000 (override with API_URL)
```

### Pilot users and roles

There is no demo data. Roles: Administrator (super user) plus four business roles — Relationship Manager, Warehouse Manager, Sales Representative and Reseller. Products are loaded from Excel with the standard template (`docs/templates/`). The pilot starts from an empty database. See **[docs/PILOT_USERS.md](docs/PILOT_USERS.md)** for the accounts, the permission matrix, the dashboards per role and the one-time clean reset.

## Tests

```bash
# Backend: pytest against a real PostgreSQL database (locking and constraints are part of the behaviour).
cd backend && pytest                         # uses TEST_DATABASE_URL or postgresql+psycopg://tyreworld:tyreworld@localhost:5432/tyreworld_test
ruff check .

# Frontend unit/component tests, type check and lint
cd frontend && npm test && npm run typecheck && npm run lint

# End-to-end (Playwright) CREATES DATA: only against a disposable local database prepared as described in
# frontend/e2e/helpers.ts (reset_to_pilot with PILOT_FORCE_PASSWORD_CHANGE=false), with the API and frontend running:
cd frontend && npm run test:e2e              # E2E_BASE_URL defaults to http://localhost:3000
```

The backend suite contains the acceptance tests from the master instructions (`tests/test_scenarios.py`, `tests/test_inventory_core.py`, `tests/test_invoicing_reporting.py`):
standard sale and replenishment, warehouse stockout, inter-reseller transfer, partial backorder fulfilment, concurrent allocation, reseller access isolation, transfer cancellation and discrepancy, and inventory reconciliation.

## Key concepts (short version)

- **Every stock change is a ledger transaction.** Stock moves between locations, including virtual ones: *supplier*, *sold*, *adjustment*, *opening*, *scrap* and *in transit*. Balances are a projection guarded by database constraints, and `GET /api/inventory/reconciliation` rebuilds them from history.
- **Available = on hand − reserved − blocked**, and can never go negative.
- **A sale** moves stock to *sold*, becomes chargeable, and raises replenishment only up to the agreed target.
- **Replenishment** reserves warehouse stock, dispatches it into transit and delivers it. It never invoices.
- **A backorder** is the part of a replenishment request still awaiting supply. Goods receipts do not close it; delivery or an authorised cancellation does.
- **A transfer** reserves at the source, collects into transit and receives at the destination. The source is owed replacement from collection onward. Nobody is invoiced for a transfer.

See [`docs/INVENTORY_RULES.md`](docs/INVENTORY_RULES.md) for the full rules.
