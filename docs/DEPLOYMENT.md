# TyreGrow — Deployment Notes

**Nothing has been deployed.** These notes prepare a low-cost production deployment. No paid service or production environment should be provisioned without explicit authorisation.

## Target topology

```
[Browser] ──HTTPS──> [Frontend: next start (Node)] ──/api/* rewrite──> [Backend: uvicorn/gunicorn] ──> [Managed PostgreSQL 16]
```

Any platform that runs one Node process, one Python process and managed Postgres works: a single small VM with Docker, or a PaaS with container support. There are no queues, caches or other services.

## Backend

```bash
pip install -r requirements.txt
alembic upgrade head                     # run as a release step before starting new code
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000
# (gunicorn is not in requirements.txt; alternatively: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2)
```

Required environment:

| Variable | Notes |
|---|---|
| `APP_ENV=production` | Enables the secret check; the pilot reset needs an extra confirmation. |
| `DATABASE_URL` | `postgresql+psycopg://user:password@host:5432/db`, with TLS required by the provider. |
| `JWT_SECRET` | Long random value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). The app refuses to start in production with the default. |
| `AUTH_COOKIE_SECURE=true` | The session cookie is sent over HTTPS only. |
| `CORS_ORIGINS` | Usually unnecessary (same origin through the frontend proxy). |
| `DEFAULT_CURRENCY`, `INVOICE_ISSUER_NAME`, `INVOICE_ISSUER_DETAILS` | Commercial settings. |
| `AUTO_ALLOCATE_ON_CREATE`, `INVOICE_DUE_DAYS_DEFAULT` | Business policy (see the decision log). |
| `PARTNER_LOW_STOCK_THRESHOLD` | Optional, default `4`. The website stock API reports warehouse stock from 1 up to this number as `LOW`. See `docs/PARTNER_API.md`. |

There is no demo data. Create the users with the one-time clean reset (`scripts/reset_to_pilot.py`, see `docs/PILOT_USERS.md`). It creates the four business accounts, one warehouse and one default tax rate, and nothing else. With `APP_ENV=production` it needs `--allow-production` and `PILOT_RESET_ALLOW_PRODUCTION=yes` in addition to `--confirm RESET-PILOT`. Never run it on a database whose data you want to keep.

Then configure these through the UI or API: the default tax rate(s), the warehouse(s), products, resellers, agreements and targets. Post opening balances as ledger transactions (Warehouse → Opening balance) rather than editing data.

## Frontend

```bash
npm ci && npm run build
API_URL=http://backend:8000 npm start -- -p 3000
```

`API_URL` is read when the rewrites are built, so set it at build time. Branding is set with `NEXT_PUBLIC_BRAND_NAME`, `NEXT_PUBLIC_BRAND_TAGLINE` and `NEXT_PUBLIC_BRAND_LOGO` (also build time).

## Operations checklist

- [ ] Nightly Postgres backups with a tested restore. The ledger is the system of record.
- [ ] Schedule `GET /api/inventory/reconciliation` (as a manager) and alert when `balanced` is false.
- [ ] Put the API behind the frontend proxy only; do not expose Postgres publicly.
- [ ] Add login rate limiting at the proxy or load balancer. It is not implemented in the application.
- [ ] If the customer website uses the stock API, add a rate-limit rule for `/api/partner/*` (about 60 requests a minute) in the Vercel Firewall, if your plan includes it. Keys are managed in Administration → Website access.
- [ ] Log retention for API access logs and the `audit_events` table.
- [ ] Review role assignments. Reseller users are read-only and scoped to one reseller.
- [ ] Before go-live, validate the open business decisions in `DECISION_LOG.md` (BC §16).

## Data migration (from spreadsheets or a legacy system)

1. Import products and resellers/locations through the API (or a one-off script using the services).
2. Set targets with the allocations endpoint. The reason is recorded, for example "Migrated from legacy".
3. Post opening balances per location. Each one is an audited ledger transaction.
4. Recreate open backorders as manual replenishment requests with the reason "Migrated backorder", using the override permission.
5. Run the reconciliation check and a stocktake of each location soon after go-live.
