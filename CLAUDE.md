# ConsignGrid — working notes for Claude sessions

Current work: **turning TyreGrow 1.11.0 into a white-label, multi-industry product**, on branch
`claude/white-label-product-plan-rrt348`. Plan: [`docs/whitelabel/01_MASTER_PLAN.md`](docs/whitelabel/01_MASTER_PLAN.md).
Progress: [`docs/whitelabel/PROGRESS.md`](docs/whitelabel/PROGRESS.md) — resume from the first step that is not ✅.

## Rules

1. One step = one commit, with `docs/whitelabel/PROGRESS.md` updated in the same commit.
2. After every step run the checks for what you touched:
   - backend: `cd backend && ruff check . && pytest -q tests/<files touched or added>` (full suite at phase end)
   - frontend: `cd frontend && npm run typecheck && npm run lint && npm test`
3. Never weaken a test. A test may change only when the behaviour deliberately changes; say why in the commit.
4. **The ledger is sacred**: do not change `backend/app/modules/inventory/service.py` (Ledger, move, reserve,
   release, block) or `docs/INVENTORY_RULES.md` sections 1–6. `/api/inventory/reconciliation` must stay balanced.
5. Migrations are additive: never edit existing ones, never drop columns, every migration has a working downgrade.
6. API changes are additive: add fields and endpoints, never rename or remove response fields.
7. Partner (dealer) isolation stays intact: partner users see only their own data; anything else returns 404.
8. **White-label**: no customer name, logo, price or data in code. Names come from the Brand Pack
   (`backend/app/core/config.py`, `frontend/src/config/branding.ts`); `tests/test_brand_pack.py` guards this.
   Today's behaviour is the default (the `tyres` industry pack).
9. Permissions live only in `backend/app/core/permissions.py`. Routers use `require(P.X)`, services scope partners,
   routers commit once per request (services never commit).
10. Read `frontend/AGENTS.md`: this Next.js version differs from older ones.
11. Run `reset_to_pilot.py`, `reset_for_uat.py` and Playwright only against a disposable local database.
