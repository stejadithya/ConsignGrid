# TyreGrow — working notes for Claude sessions

Current work: **UAT findings, release 1.11.0**, on branch `feature/uat-findings-1.11`.
Progress, decisions and the acceptance matrix: [`docs/plans/UAT_FINDINGS_PROGRESS.md`](docs/plans/UAT_FINDINGS_PROGRESS.md).
Resume from the first step in that log that is not ✅.

## Rules (Part A of the plan)

1. Work on `feature/uat-findings-1.11` (from `main`). Never commit to `main`, never push, never deploy unless asked.
2. Do exactly what the step says. Anything else that looks wrong goes under "Noticed, not changed" in the log, unfixed.
3. One step = one commit, message `P<phase>.<step>: <what>`, with the progress log updated in the same commit.
4. After every step run the checks for what you touched:
   - backend: `cd backend && ruff check . && pytest -q tests/<files touched or added>`
   - frontend: `cd frontend && npm run typecheck && npm run lint && npm test`
   After every phase run the whole backend suite and the frontend checks. A phase is not done while anything is red.
5. Never weaken a test. Only the tests a phase lists as deliberately changing may be updated, with the reason in the commit message.
6. Do not change the inventory ledger core (`backend/app/modules/inventory/service.py`: Ledger, move, reserve, release, block)
   or `docs/INVENTORY_RULES.md` sections 1–6. Every stock movement goes through the existing functions.
   `/api/inventory/reconciliation` must stay balanced.
7. Migrations are additive: new files from 0011. Never edit 0001–0010, never drop columns, every migration has a working
   downgrade, and `alembic check` shows no drift.
8. API changes are additive: add fields and endpoints, never rename or remove response fields. When a request body changes,
   update every caller (frontend, backend tests, e2e helpers).
9. Dealer isolation stays intact: dealers never see warehouse figures, other dealers, internal rejection reasons or Xero
   numbers. New endpoints scope dealer users to their own `reseller_id` and return 404 for anything else.
10. Read `frontend/AGENTS.md`: this Next.js version differs from older ones. Read `frontend/node_modules/next/dist/docs/`
    before using a Next.js API not already used in the repo.
11. On screen say "Dealer" (never "reseller"). Name tyres by model and size with the SKU alongside. Plain, friendly tone.
12. Run `reset_to_pilot.py`, `reset_for_uat.py` and Playwright only against a disposable local database.
13. Permissions live only in `backend/app/core/permissions.py`. Routers use `require(P.X)`, services scope dealers,
    routers commit once per request (services never commit).
