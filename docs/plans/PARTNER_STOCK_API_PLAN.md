# Website stock API (Stage A): plan for approval, not implemented

Branch `feature/partner-stock-api`, from `main` at 0715c69.

**Goal:** the TyreGrow customer website's server asks TyreGrow, at any time, whether a SKU can be sold from the
warehouse. The answer is **In stock / Low / Out**, never a quantity.

**Decided:**
- Stage A only: read-only, no orders, no reservations.
- Server-to-server.
- Status bands instead of numbers.

## 1. What the website calls

All requests carry the header `X-API-Key: tg_live_…`. There are no cookies, and CORS is not needed, because the caller is
the website's server, not a browser.

| Call | Returns |
|---|---|
| `GET /api/partner/v1/stock` | Every active SKU: `[{ "sku", "name", "size", "status" }]`, plus `generated_at` |
| `GET /api/partner/v1/stock?sku=103294&sku=104010` | Only those SKUs (up to 100 per call) |
| `GET /api/partner/v1/stock/{sku}` | One SKU, or 404 if TyreGrow doesn't know it |

`status` is one of `IN_STOCK`, `LOW` or `OUT`:

| Status | Rule (warehouse available = on hand − reserved − blocked, summed over warehouse locations) |
|---|---|
| `OUT` | 0, or the product is inactive in the catalogue |
| `LOW` | 1 to 4. This is the same threshold as "Low" on the Warehouse screen, set by the `PARTNER_LOW_STOCK_THRESHOLD` environment variable |
| `IN_STOCK` | 5 or more |

- Only warehouse stock counts: dealer consignment stock, transit and sold stock are ignored.
- The response never contains a quantity, location, dealer, price, internal reason or Xero number.
- Errors are plain JSON: 401 for a missing, unknown or revoked key; 404 for an unknown SKU; 422 for more than 100 SKUs.

**Freshness:** each answer is computed live from the stock ledger with one read-only query. Responses carry
`Cache-Control: private, max-age=60`, so the website may reuse an answer for up to 60 seconds. It is recommended to fetch the
full list every minute or so, rather than once per page view.

## 2. API keys

- New table `partner_api_keys`, added by migration `0017` (additive, with a working downgrade). Columns:
  - name (for example "Customer website")
  - key prefix (for display)
  - SHA-256 hash of the key
  - created by and created at
  - last used at
  - revoked at
- The full key is shown **once**, when it is created; only its hash is stored.
- A key can be revoked at any time. A new key can be issued before the old one is revoked, so rotation needs no downtime.
- Managed in **Admin → Website access**: create, see last used, revoke. Allowed for **Administrators only**, through a new
  `P.PARTNER_KEYS_MANAGE` permission in `core/permissions.py`.
- Every key creation and revocation is written to the audit log.

## 3. What does not change

- The stock ledger, its functions and `docs/INVENTORY_RULES.md`. The API only reads; reconciliation stays balanced.
- Existing endpoints, screens, permissions and roles. New endpoints only.
- Dealer isolation. The key gives access to warehouse status bands and nothing else.

## 4. Abuse protection

- Keys are long and random (32 bytes); a missing or bad key is refused before any stock query runs.
- Rate limiting: serverless instances on Vercel don't share memory, so an in-app limit would be unreliable. Recommendation:
  add a Vercel Firewall rate-limit rule on `/api/partner/*` (about 60 requests per minute). Whether that is available
  depends on your Vercel plan. If it isn't, Stage A ships without a limit, which is acceptable for a single trusted caller with a
  revocable key; this can be revisited later.

## 5. Tests

**Backend (pytest):**
- 401 for no key, a wrong key and a revoked key.
- Bands at 0 / 1 / 4 / 5 available, with reserved and blocked subtracted.
- Dealer stock ignored.
- Inactive product reported as `OUT`.
- `?sku=` filter, the 100 limit and 404.
- No quantity or location fields in the response.
- Key stored only as a hash and shown once.
- Non-admin gets 403 when managing keys.
- `last_used_at` updates on use.
- Reconciliation unchanged.

**Frontend:**
- A unit test for the Website access tab.
- A browser test: an Administrator creates a key, sees it once and revokes it.

**Then:** the full backend suite, `alembic check`, typecheck, lint, unit tests, all browser scenarios and the production
build.

## 6. Files expected

- `backend/app/modules/partner/` (new): router, service, schemas, models.
- `backend/alembic/versions/0017_partner_api_keys.py` (new).
- `backend/app/core/permissions.py`: `PARTNER_KEYS_MANAGE`.
- `backend/app/core/config.py`: `PARTNER_LOW_STOCK_THRESHOLD`.
- `backend/app/main.py`: register the router.
- `backend/tests/test_partner_api.py` (new).
- `frontend/src/app/(app)/admin/page.tsx`: Website access tab.
- `frontend/src/lib/types.ts`: key types.
- `docs/PARTNER_API.md` (new): a one-page guide for the website developer, with curl examples.
- `docs/DEPLOYMENT.md`: the new environment variable and the firewall recommendation.

## 7. Cost and effort

- Effort: about 1–2 working sessions, plus a few hours for your website developer.
- Cost: no new software or licences. One extra request per minute (or per cache period) from the website runs on the
  existing Vercel project and database. The Vercel Firewall rule may depend on your plan.
