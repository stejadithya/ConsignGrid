# TyreGrow pilot: users, roles and clean start

The two-week business pilot runs on **real** data entered by four business profiles. The database starts **empty**, with no demo or sample records, and everything entered during the pilot is kept across redeployments.

> Passwords are never stored in this repository. Each account gets a temporary password from the set-up step and must choose its own at first sign-in.

## 1. Pilot accounts

The emails below are placeholders for the GitHub secrets you set (see §5). Fill in the real addresses when you set them.

| Role | Login | Purpose | Permission summary |
|---|---|---|---|
| **Administrator** (super user) | value of `PILOT_ADMIN_EMAIL` | Manages everything: users and roles (including other administrators), product master and Excel imports, stock, purchasing, resellers, invoicing, reports, audit log, pilot feedback | **Every permission.** Only an Administrator can create, promote to or change an Administrator account. |
| **Relationship Manager** | value of `PILOT_RM_EMAIL` | The head of TyreGrow and its administrator. Primary dealership/customer relationship role: reseller accounts, customer stock, shortages, urgent requests, transfers and invoicing | Resellers (create/edit, targets, prices), consignment stock, sales & stocktakes (record and approve), replenishment (request, manage, cancel, override), transfers (request, approve, execute), invoices (create, issue, void), reports. Product catalogue: read and **import from Excel**. **Administers TyreGrow**: user logins, audit log, pilot feedback review and settings (Administration page). No warehouse receipts, adjustments or purchasing. |
| **Warehouse Manager** | value of `PILOT_WM_EMAIL` | Broad operational and management authority over stock, supply and fulfilment ("what does the warehouse need to do today?") | Product master (create/edit/import), warehouse stock (receive, adjust, block, write off, opening balances), purchasing & shipments, replenishment (allocate, dispatch, cancel), backorders, transfers (approve, execute, resolve), stocktakes (approve), reports. **Not an administrator**: no user logins, audit log, feedback review or settings. No invoicing. |
| **Sales Representative** | value of `PILOT_SR_EMAIL` | Dealership employee visiting reseller sites | View authorised resellers and their consignment stock, perform stocktakes, record reported sales, request replenishment, see backorder status, request transfers, confirm deliveries. No purchasing, invoicing, adjustments or administration. |
| **Finance Manager** | created under Administration → Users | Billing: what to invoice in Xero and the Xero numbers | Invoices (create, mark as invoiced, void, Xero numbers), sales (view only), dealers (view only), reports. No stock actions, no administration. |
| **Reseller** | value of `PILOT_RESELLER_EMAIL` | The pilot reseller business | **Own organisation only**: consignment stock, report a sale, request replenishment (within agreed stock levels, not urgent), own backorders, deliveries, transfers, invoices and account activity. Never sees other resellers, warehouse-wide stock, dealership reports, purchasing or administration. |

Beyond the Administrator, there are no other business roles. The previous demo roles (System administrator, Dealership manager, Warehouse operator, Finance) have been removed. Migration `0003` maps any existing accounts:

| Old role | New role |
|---|---|
| Dealership manager | Relationship Manager |
| Warehouse operator | Warehouse Manager |
| System admin | Warehouse Manager, and the account is deactivated |
| Finance | Relationship Manager, and the account is deactivated |

The clean reset removes all of these old accounts anyway.

## 2. Role / permission matrix

✅ = allowed · — = not allowed. Every rule is enforced by the API; the navigation only mirrors it.

The **Administrator** has every capability below (and manages administrator accounts); it is not repeated per row.

| Capability | Relationship Mgr | Warehouse Mgr | Sales Rep | Reseller | Finance Mgr |
| --- | :-: | :-: | :-: | :-: | :-: |
| Dashboard (role-specific) | ✅ | ✅ | ✅ | ✅ own | ✅ |
| Products: view | ✅ | ✅ | ✅ (pickers; no menu entry) | ✅ (pickers only) | ✅ (pickers only) |
| Products: add one at a time | ✅ | ✅ | — | — | — |
| Products: edit | ✅ | ✅ | — | — | — |
| Products: import from Excel (standard template) | ✅ | ✅ | — | — | — |
| Dealer price list (reference document) | ✅ | ✅ | ✅ (no menu entry; `/products`) | — | ✅ |
| Product cost prices | ✅ | ✅ | — | — | — |
| Warehouse stock: receive, adjust, block, write off | ✅ | ✅ | — | — | — |
| Purchasing & shipments | ✅ | ✅ | — | — | — |
| Resellers: view | ✅ | ✅ | ✅ | ✅ own | ✅ |
| Resellers: create / edit, targets, prices | ✅ | — | — | — | — |
| Consignment stock: view | ✅ | ✅ | ✅ | ✅ own | ✅ |
| Record / report a sale | ✅ | — | ✅ | ✅ own, agreed price only | — (views sales only) |
| Non-consignment sale (from warehouse) | ✅ | ✅ | — | — | — |
| Initial stock for an existing reseller | ✅ | ✅ | — | — | — |
| Correct a dealer's initial stock (with a reason; until the first stock check, at most 30 days) | ✅ | — | — | — | — |
| Unlock a user locked after 5 wrong passwords | ✅ | — | — | — | — |
| Move a dealer's stock check (up to 14 days, with a reason) | ✅ | ✅ | ✅ own dealers | — | — |
| Record "Received at the warehouse" on a via-warehouse transfer | ✅ | ✅ | — | — | — |
| Reports → Stock corrections | ✅ | ✅ | ✅ | — | ✅ |
| Reverse an uninvoiced sale | ✅ | — | — | — | — |
| Stocktake: count | ✅ | ✅ | ✅ | — | — |
| Stocktake: approve (counts from before v1.4.0) | ✅ | ✅ | — | — | — |
| Stock check, tyres not found: invoice now | ✅ on behalf, with reason | ✅ on behalf, with reason | — | ✅ own | — |
| Stock check: ask for a re-check, raise a dispute | — | — | — | ✅ own | — |
| Stock check: start a re-count | ✅ | ✅ | ✅ | — | — |
| Replenishment: request | ✅ | ✅ | ✅ (reserves nothing until staff allocate) | ✅ own, within target, not urgent (reserves nothing until staff allocate) | — |
| Replenishment: approve (with details), send to RM, reject | ✅ | ✅ | — | — | — |
| Replenishment: allocate, plan, release | ✅ | ✅ | ✅ | — | — |
| Replenishment: cancel / override target | ✅ | ✅ | — | — | — |
| Pick & dispatch; mark ready and ship a replenishment request | ✅ | ✅ | — | — | — |
| Confirm delivery receipt | ✅ | ✅ | ✅ | ✅ own deliveries | — |
| Stock requests: view | ✅ all | ✅ all | ✅ all resellers | ✅ own | — |
| Stock requests: create, edit draft, submit, cancel before decision | ✅ | ✅ | ✅ on behalf of any reseller | ✅ own, not urgent | — |
| Stock requests: review, approve, partially approve, reject (Central Team; approval details required) | ✅ | ✅ | — | — | — |
| Stock requests: send to a Relationship Manager / hand back | — (receives; hands back) | ✅ | — | — | — |
| Stock requests: "Please call me" | — | — | ✅ | ✅ own | — |
| Stock requests: reserve backorder / release reservation (Central Team) | ✅ | ✅ | — | — | — |
| Stock requests: mark ready for shipment, ship | ✅ | ✅ | — | — | — |
| Inventory views: stock overview, allocation, movement | ✅ | ✅ | ✅ | — | ✅ (API; no menu entry) |
| Notifications (in-app bell, own only) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Transfers: view | ✅ | ✅ | ✅ | ✅ own side only | — |
| Transfers: request | ✅ | ✅ | ✅ | — | — |
| Transfers: approve, arrange pick-up (rep or courier) | ✅ | ✅ | — | — | — |
| Transfers: collect / receive | ✅ | ✅ | ✅ (only the assigned rep when one is assigned) | ✅ receive, own | — |
| Invoices: view | ✅ | — | — | ✅ own | ✅ |
| Invoices: create invoice record / mark as invoiced in Xero (Xero number) / void | ✅ | — | — | — | ✅ |
| Invoice and Xero numbers on sales | ✅ | — (Invoiced ✓ / Not yet) | — (Invoiced ✓ / Not yet) | invoice number only, no Xero number | ✅ |
| Reports | ✅ | ✅ | API only (dashboard) | own transaction history and own "By dealer by SKU" | ✅ |
| Administration: users (incl. phone, hand over, replace someone) | ✅ | — | — | — | — |
| Administration: audit log | ✅ | — | — | — | — |
| Administration: pilot feedback review | ✅ | — | — | — | — |
| Pilot feedback: submit | ✅ | ✅ | ✅ | ✅ | ✅ |
| Change own password | ✅ | ✅ | ✅ | ✅ | ✅ |

Since 1.11.0 the Relationship Manager has everything the Warehouse Manager has (P-028), and the Finance Manager's permissions are a subset of the Relationship Manager's (P-029). Replenishment approvals use `replenishment.approve` (P-035). A user cannot be deactivated while dealers, hand-overs or approvals are still theirs (P-044).

Source of truth: `backend/app/core/permissions.py`. Tests: `backend/tests/test_pilot.py`, `backend/tests/test_role_hierarchy.py`.

## 3. Dashboards and navigation by role

Every number on a dashboard opens the screen behind it.

| Role | Dashboard focus | Navigation |
|---|---|---|
| Relationship Manager | **Owner's overview** (blue). Linked headline figures: sold not invoiced, sales this month, stock at dealers, warehouse available, waiting for supply. "Decisions waiting for you": stock requests and transfers to approve, tyres to invoice, locations below agreed level, stock checks waiting for the dealer, dealers on hold. Then each dealer this month (sold, value, in stock, waiting), needs attention and recent activity. | Dashboard · Consignment (Pending Approval, Approved Requests, Shipments, All Requests, My Requests, Create Request) · Customers (Resellers, Consignment Stock, Sales & Stocktakes) · Operations (Replenishment, Backorders, Stock Transfers, Purchasing & Shipments) · Inventory (Stock Overview, Check Stock, Stock Allocation, Stock Movement, Warehouse) · Catalogue (Products) · Commercial (Invoices) · Insights (Reports) · System (Administration, Settings) |
| Warehouse Manager | **Warehouse floor** (amber). Linked figures: on hand, available, reserved, blocked, incoming. "Today's jobs": approve stock requests, pick and ship, find tyres from other dealers, collect transfers, receive supplier deliveries, deliveries on the road. Then attention, out of stock with dealers waiting, and expected supplier deliveries. | Dashboard · Inventory (Stock Overview, Stock Allocation, Stock Movement, Products, Warehouse, Consignment Stock) · Consignment (Pending Approval, Approved Requests, Shipments, All Requests, My Requests, Create Request) · Operations (Replenishment, Backorders, Stock Transfers, Purchasing & Shipments, Stocktakes & Sales) · Insights (Reports) |
| Sales Representative | **Field day** (green). Linked figures: my dealers, stock checks due (none in 30 days), to hand over, sold this month, waiting for supply. "Today's visits", hand-overs in your vehicle, my dealers (last stock check, sold, in stock, waiting), attention and activity. It uses the dealer's assigned sales rep; if none are assigned, all active dealers are shown. | Dashboard · Consignment (My Requests, Create Request, Approved Requests, Shipments, All Requests) · Customers (Resellers, Consignment Stock, Sales & Stocktakes) · Operations (Replenishment, Backorders, Stock Transfers) · Inventory (Stock Overview) |
| Reseller | **My shop** (purple). Figures: in my shop, on the way, waiting for supply, sold this month. "What to do next": confirm deliveries, ask for tyres running low, check waiting orders, report sales. Then stock requests, stock requiring attention, recent sales, deliveries and activity. | My Dashboard · My Stock (Consignment Stock) · Actions (Report Sale, Request Stock) · Tracking (My Requests, Backorders, Deliveries, Stock Transfers, My account) · Commercial (Invoices) |
| Finance Manager | **Billing** (teal). Figures: tyres sold and not invoiced, dealers to invoice, invoice records waiting for a Xero number, invoiced this month. Then sold-not-invoiced by dealer, records waiting for a Xero number and recently invoiced. | Dashboard · Commercial (Invoices, Sales) · Customers (Dealers) · Insights (Reports) |

## 4. What a clean pilot database contains

After the reset, these are the only records:

| Record | Count | Why it exists |
|---|---|---|
| Users | 4 (3 if the reseller is not configured) | The pilot accounts |
| System locations | 6 (`SYS-TRANSIT`, `SYS-SUPPLIER`, `SYS-SOLD`, `SYS-ADJUSTMENT`, `SYS-OPENING`, `SYS-SCRAP`) | Counterparts of the double-entry stock ledger, created by migration `0001`. Not business data. |
| Warehouse location | 1 (`PILOT_WAREHOUSE_CODE`, default `WH-MAIN`) | Receipts and dispatches need a warehouse |
| Tax rate | 1 (`PILOT_TAX_CODE`, default GST 15%) | Sales and invoices snapshot a tax rate. The price list is in NZD and quotes GST. |
| Reseller organisation + location | 1 + 1 (only if `PILOT_RESELLER_BUSINESS_NAME` and `PILOT_RESELLER_ACCOUNT_REF` are set) | The real pilot reseller the Reseller user belongs to |
| Audit events | 1–2 | "Database reset to clean pilot state" (and "reseller created") |
| Products, stock, ledger, targets, prices, sales, stocktakes, replenishment, backorders, deliveries, transfers, purchase orders, receipts, invoices, feedback | **0** | Real activity starts from zero |
| Reference documents | 1 | TyreGrow Dealer Price List (effective 7 July 2026), an image served by the API. It is not a database record and never creates products or stock. |

Set `DEFAULT_CURRENCY=NZD` on the API project in Vercel (Settings → Environment Variables), then redeploy. The price list is in NZD.

## 5. One-time reset to the clean pilot state

The reset **deletes all data and users**. It never runs automatically: deployments, migrations and the API do not call it.

### A. GitHub Actions (recommended)

1. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**. Add:

   | Secret | Required | Example |
   |---|---|---|
   | `PILOT_RM_EMAIL` | yes | the Relationship Manager's work email |
   | `PILOT_RM_NAME` | recommended | the person's full name (shown in the app) |
   | `PILOT_RM_PASSWORD` | yes in Actions | a temporary password, at least 10 characters |
   | `PILOT_WM_EMAIL`, `PILOT_WM_NAME`, `PILOT_WM_PASSWORD` | same as above | Warehouse Manager |
   | `PILOT_SR_EMAIL`, `PILOT_SR_NAME`, `PILOT_SR_PASSWORD` | same as above | Sales Representative |
   | `PILOT_RESELLER_EMAIL`, `PILOT_RESELLER_NAME`, `PILOT_RESELLER_PASSWORD` | for the reseller user | the reseller's contact |
   | `PILOT_RESELLER_BUSINESS_NAME` | for the reseller user | the real reseller business name |
   | `PILOT_RESELLER_ACCOUNT_REF` | for the reseller user | e.g. `R001` (letters, digits, `-`, `_`, `.`) |

   Optional repository **variables** (Variables tab): `PILOT_WAREHOUSE_CODE`, `PILOT_WAREHOUSE_NAME`, `PILOT_TAX_CODE`, `PILOT_TAX_NAME`, `PILOT_TAX_RATE` (for example `0.15`).
2. GitHub repo → **Actions → Database setup → Run workflow**, then in the **pilot_reset** box type exactly `RESET-PILOT` → **Run workflow**.
3. The log shows the contents before and after (all business counts 0). Passwords are masked.
4. Give each person their email and temporary password privately. At first sign-in they choose their own password.

When the box is left empty, the same workflow only applies migrations and shows counts. It never deletes anything. Use that for future updates.

### B. From a computer

```bash
cd backend
export DATABASE_URL='<UNPOOLED Neon URL>'
python -m scripts.reset_to_pilot --dry-run                      # shows counts, changes nothing
export PILOT_RM_EMAIL=… PILOT_WM_EMAIL=… PILOT_SR_EMAIL=… PILOT_RESELLER_EMAIL=…
export PILOT_RESELLER_BUSINESS_NAME='…' PILOT_RESELLER_ACCOUNT_REF=R001
python -m scripts.reset_to_pilot --confirm RESET-PILOT
```

When run from a computer without `PILOT_*_PASSWORD`, temporary passwords are generated and printed **once**.

### Creating the Administrator (keeps all data)

1. Add the secrets `PILOT_ADMIN_EMAIL`, `PILOT_ADMIN_NAME` and `PILOT_ADMIN_PASSWORD`. The password is the **default password**: at least 10 characters, chosen by you, never stored in Git.
2. Go to **Actions → Database setup → Run workflow**, tick **create_admin**, and leave **pilot_reset** empty.
3. Sign in with that email and default password. TyreGrow asks for a new password straight away.

Running it again is safe: it keeps the same single account and does not reset its password. From a computer, `python -m scripts.create_admin --reset-password` replaces the password, which must then be changed at the next sign-in.

The admin secrets are also used by the clean reset when present, so the Administrator is created together with the four pilot accounts.

### Safety guards

- `--confirm RESET-PILOT` is required. Anything else exits without changes.
- With `APP_ENV=production`, it also needs `--allow-production` **and** `PILOT_RESET_ALLOW_PRODUCTION=yes`.
- In GitHub Actions, generated passwords are refused (logs are retained), so you must supply them as secrets.
- `PILOT_FORCE_PASSWORD_CHANGE=false` is a test-only switch and is refused for staging or production.
- The backend test suite refuses to run against any database that is not local and named `*_test`.

### After the reset

- Real pilot transactions persist. Redeploying or running migrations never removes them.
- Add more users: Relationship Manager → **Administration → Users → New user**. New users must change their password at first sign-in.
- To onboard another reseller: the Relationship Manager creates the reseller account, then adds its user under **Administration → Users** (role Reseller, linked to that reseller).

## 6. Product catalogue from Excel

Products → **Import from Excel** is available to the Administrator, the Relationship Manager and the Warehouse Manager.

1. **Download the standard template**: Products → **Excel template**. A copy is also in `docs/templates/TyreGrow_SKU_Import_Template.xlsx`. Use this one format for every future import.

   | Column | Required | Notes |
   |---|---|---|
   | SKU Code | yes | Unique code; letters, digits, `. _ / -` (no spaces) |
   | SKU Description | yes | e.g. `205/55R16 ECODRIVE TL 91H CEAT`. Size, pattern, load/speed and brand are read from it. |
   | Dealer Price (excl. GST & Stewardship) | yes | NZD, the price charged to resellers |
   | RRP (incl. GST, excl. Stewardship) | no | NZD |
   | Brand, Pattern, Width (mm), Aspect Ratio, Rim Diameter (in), Load Index, Speed Rating | no | Override what is read from the description |
   | Barcode, Cost Price (excl. GST), Active (Y/N) | no | Barcode must be unique; Active N hides the product |

2. **Choose the filled file → Check file.** Nothing changes yet. Every row is shown as New, Update, No change or Error, with the reason.
3. **Import N products.** Valid rows are saved in one go; rows with errors are skipped. New SKU codes are created. Existing codes get their description and prices updated. Tyre size is never changed by an import.
4. Importing creates **products only**. Warehouse and consignment stock stay at 0 until goods are received, delivered or posted as opening balances.

The importer also accepts the dealer price list layout (title lines above the header are fine).

**July 2026 dealer price list.** The supplied file is stored in `backend/data/products/tyregrow-dealer-price-list-2026-07-07.xlsx`. It has 39 SKU rows:

- **38 import.** SKU 105592 (`195R15C`) has no stated aspect ratio, so 80 is assumed (the standard for metric commercial sizes) and shown as a note.
- **1 is rejected.** Its SKU code and size are obscured in the source photo (`… ENDURADRIVE TL 108/106T`, dealer price 147, RRP 375). Add it with **Add product** once the code is known.

You can load the list in either of two ways:

- **Products → Import from Excel** with that file.
- GitHub **Actions → Database setup → tick "import_skus"**. This only adds or updates products and keeps all other data.

## 7. Pilot feedback

Every user can open **user menu → Pilot feedback** and record:

- page/module
- type: Issue, Improvement, Question or Other
- a description

The server adds the user, role and timestamp. The Relationship Manager reviews all feedback under **Administration → Pilot feedback**. The data is in the `pilot_feedback` table, and each submission is also written to the audit log.
