# White-label progress log

Branch: `claude/white-label-product-plan-rrt348`. One step = one commit. Status: ✅ done · 🔄 in progress · ⏳ next ·
⬜ planned. Checks after every step: backend `ruff check . && pytest`, frontend `npm run typecheck && npm run lint &&
npm test`.

| Step | What | Status | Notes |
|---|---|---|---|
| 0.1 | Import TyreGrow 1.11.0; remove the previous customer's price list, business case and UAT PDFs; reference documents per deployment; fictional sample catalogue | ✅ | Baseline green: 301 backend tests, 60 frontend tests. Two tests changed because their fixture was confidential. |
| 0.2 | Master plan, industry analysis, go-to-market, customer playbook | ✅ | `docs/whitelabel/` |
| 1.1 | Brand Pack: neutral default brand (ConsignGrid), placeholder logo and icons, accent override, product vs company name, brand-driven file names, guard test against the old brand | ✅ | 305 backend tests, 60 frontend tests, production build verified with a demo brand (screenshots in `img/`). |
| 1.2 | Vocabulary layer: item / partner / site words from the Industry Pack on screens, notifications, emails, PDFs, exports and errors; "dealership" wording replaced by the company name | ✅ | ~430 frontend and ~135 backend strings converted by AST-based codemods, then reviewed by hand (2 code values reverted, 12 module-level labels made lazy). Tyres pack reproduces the old wording exactly: all existing tests unchanged. 312 backend, 64 frontend tests. Verified in the running app with the medical pack (screenshots in `img/`). |
| 1.3 | Industry Pack registry (9 packs, `TERMS_OVERRIDES`) + `GET /api/config/public` and `/api/config/industry-packs`; frontend `ConfigProvider` loads words at start-up | 🔄 | Words are run-time. Still build-time: brand name, logo and accent (`NEXT_PUBLIC_BRAND_*`) — move them to the endpoint together with pooled tenancy (3.1). |
| 1.4 | Generic items: pack-defined attributes (`products.attributes` JSONB, migration 0022), tyre columns optional, validation per pack, spec and display name from the pack, attribute search, attribute-driven product form / detail / list, generic Excel template + import + export, fictional sample catalogues (medical, auto parts, tiles) | ✅ | Tyres pack unchanged (same importer, template, validation, wording). Migration tested up → down → up, `alembic check` clean. 322 backend, 66 frontend tests. Verified in the running app with the medical pack (screenshots in `img/`). |
| 1.5 | "Xero" → "accounting system" in the UI | ⏳ | |
| 1.6 | Deployment kit (Dockerfiles, prod compose, new-customer script) | ⬜ | |

## Noticed, not changed
- OpenAPI field descriptions and a few class-level strings still say "dealer"/"tyre" (evaluated once at import, so they
  cannot follow the pack). They only show in `/api/docs`; rewrite them neutrally when the API docs are branded.
- The tyres pack keeps its own importer/template (`catalogue/importer.py`, `template.py`): it reads size, load and
  speed from free-text descriptions, which no other pack needs. Every other pack uses `catalogue/generic_import.py`.
- Attribute *values* for lot / serial / expiry ("Tracking", "Shade / batch matters") are descriptive only until Phase
  2.1 adds real lot and serial tracking to the ledger.
- Reports' tyre-size filters (width / aspect / rim on `/reports/...` and the consignment page) are simply unused by
  other packs; replace them with attribute filters when a pilot asks.
- Frontend tests and backend test fixtures still use real tyre brand names (e.g. CEAT) as sample data. They are
  public product names, not customer data; they can be swapped for fictional ones at any time.
- `docs/` (outside `docs/whitelabel/`) still describes TyreGrow: requirements, UAT plans, decision log and Vercel
  deployment. Kept as engineering history; to be rewritten as product documentation in Phase 1.6.
- The `.github/workflows/db-setup.yml` workflow is the old customer's Neon setup. Keep for reference; replace in 1.6.
- Local database and user names are still `tyreworld` (dev only, invisible to customers). Rename with the deployment
  kit in 1.6.
