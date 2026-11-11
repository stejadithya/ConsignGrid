# TyreGrow release notes

## Unreleased — One search box across the app

**No database migration.**

* **Search everything** from the top bar (press **/** to start typing; on a phone, tap the search icon). Results appear as you type, grouped:
  * **Documents** by number, however it is typed ("SRQ-000002", "srq 2" or "000002"): stock requests, replenishment requests, deliveries, transfers, sales, stock checks, stock movements, invoice records (and the Xero number for the Relationship Manager, Finance Manager and Administrator), purchase orders (and the supplier reference) and goods receipts.
  * **Dealers** by name, trading name, account reference, contact, phone, email, shop name, city or code.
  * **Tyres** by SKU, size typed loosely ("195 65") or brand and pattern.
  * **People** (Relationship Manager and Administrator) by name or email, with a "Locked" status.
* **Enter** on an exact number opens it straight away; arrow keys move through the results.
* Everyone only finds what they could already open. Dealers find only their own requests, deliveries, transfers, sales, stock checks and invoice records, never another dealer, warehouse documents or staff.
* Opening a delivery, goods receipt, stock movement or person from the search goes straight to that record's row.


## Unreleased — UAT round 2: sign-in, dealer onboarding, transfers, stock check schedule

**Database migrations:** `0018` to `0021` (all additive: new columns with defaults or empty, and two new tables). After merging, run **Database setup** with the boxes **empty**.
**New optional settings:** `LOGIN_MAX_ATTEMPTS` (5), `LOGIN_LOCK_MINUTES` (15), `PASSWORD_HISTORY` (3), `STOCK_CHECK_EVERY_DAYS` (30), `STOCK_CHECK_MOVE_DAYS` (14).

### Sign in & find your way
* Passwords: at least 10 characters, any letters, numbers, spaces or symbols. A password longer than 72 bytes (about 72 plain characters, fewer with accented letters or emoji) used to fail with a server error; it now gets a plain message.
* **5 wrong passwords in a row lock the account for 15 minutes.** The sign-in page says so. A Relationship Manager or Administrator sees **Locked** in Administration → Users and can **Unlock now**; setting a new password also unlocks it.
* A new password can't be the current one or either of the two before it.
* The email is matched without capitals or spaces.

### Adding a dealer & login
* **Account reference (automatic)** is clearly locked and sits under the business name.
* **Dealer name first everywhere:** shop pickers read "Roskill Tyres — Main shop (Auckland) · code"; tables and cards lead with the dealer's name, with shop, city and code underneath. The address is only on delivery documents.
* An existing dealer's Dealer history now says "Joined holding TyreGrow stock".

### Tyres for a new dealer
* A **new dealer's** first stock comes from the warehouse: the New dealer form takes an optional **first order**, saved as a stock request that goes for approval, picking and delivery by the Sales Rep. The dealer page offers **Order stock**. Initial stock (typed or Excel) is only for a dealer who already holds TyreGrow stock. Dealers added before keep working as before.

### Receiving tyres
* Purchase order lines and goods receipts show the tyre name and size with the SKU.

### Stock transfers
* When approving a stock request, the rest of a line can be backordered, rejected or **arranged from another dealer**: a transfer request is raised straight away, linked to the backorder. Stock request backorders also get **Cover with a transfer** (on the request and on Backorders).
* **Route per transfer:** direct to the dealer, or **via the warehouse**. Via the warehouse, the rep collects (who handed over, photos), the warehouse records **Received at the warehouse** (what arrived, condition, photos), and only then does the rep deliver (received by, notes, photos). The tyres stay "in transit" throughout. The rep's dashboard shows "to the warehouse" then "to deliver"; the Warehouse Manager's shows "Check transfers at the warehouse".

### Stock checks at dealers
* Every dealer shop is due a stock check 30 days after its last one. The Sales Rep (for their dealers), Warehouse Manager or Relationship Manager can **move** it up to 14 days ahead with a reason; the Warehouse and Relationship Managers are told.
* The daily job reminds the rep on the due date, and tells the Warehouse and Relationship Managers (and the rep), weekly, about shops with no check for 30+ days.
* "Stock checks due at dealers" on the Warehouse and Relationship Manager dashboards, "My stock checks" for the Sales Rep, "Next stock check" on the dealer's Stocktakes tab.


## Unreleased — Correct a dealer's initial stock

**No database migration.** New optional setting `INITIAL_STOCK_CORRECTION_DAYS` (default **30**).

### New
* **Correct initial stock** (Relationship Manager and Administrator only): on the dealer's **Dealer history** tab, fix a wrongly entered initial stock: change a quantity, remove a tyre (0) or add a missed one, and say what was wrong. The original entry is kept and the correction is shown beside it. Tyres already sold, reserved or blocked can't be corrected away. Allowed until the first stock check at that shop, and for 30 days.
* Administrators and Finance Managers are told about every correction. **Reports → Stock corrections** lists them all: when, dealer, shop, tyre, before → after, who and why. They also show in the change history, the dealer's transaction history and "Where did this tyre come from?".

## 1.11.0 — UAT findings: approvals, fulfilment, Xero, stock checks, handover (2026-10-21)

**Database migrations:** `0011` to `0016` (all additive: new columns and one new table for agreement copies; nothing is removed). After merging, run **Database setup** with the uat_reset and pilot_reset boxes **empty**.
**New setting:** `STOCKTAKE_FIND_DAYS` (default **5**): days a dealer has to find tyres not found at a stock check. `STOCKTAKE_CONFIRM_HOURS` is still accepted but no longer used for new checks.
**New daily job:** `/api/stocktakes/auto-invoice/cron` (in `backend/vercel.json`, 04:05 UTC). It uses the existing `CRON_SECRET`; nothing to add if the nightly photo clean-up already runs. See `docs/DEPLOY_VERCEL.md`.

### New
* **Finance Manager** role: invoice records and Xero numbers, read-only sales, dealers and reports, no stock actions.
* **Pop-up notifications** with a short sound (switch it off in your user menu), the unread count in the browser tab, and optional desktop alerts.
* **New dealer form:** the account reference is made for you (e.g. AKT-AUC-001); phone, email, billing address and sales rep are required; add **several shops**, each with its own delivery address (codes AKT-AUC-001-01, -02, …); create the dealer's **login** at the same time (the temporary password is shown once); load their existing stock from **Excel**; attach a copy of the **signed agreement** (PDF or image, up to 5 MB).
* **Export all SKUs** to Excel in the import layout, edit, and import it again (Relationship and Warehouse Managers).
* **Stock requests:** a printable **pick sheet**; **Approve…** asks who approved, how, who you spoke to and why; the Warehouse Manager can **send it to a Relationship Manager**, who approves or hands it back; the approval shows how many of the same tyre the dealer already holds.
* **Any part of an order that can't be supplied** shows the dealer a kind standard message (never the internal reason), with **Please call me**.
* **Replenishment requests have their own flow:** approve with details, send to the RM, reject (kind message), mark ready, ship (courier or sales rep) and confirm delivery, all on the request. Dealers and reps can add a **note for the approver**; Pick & dispatch shows **Ready**.
* **Transfers carried by a sales rep or a courier:** arrange the pick-up when approving (or later); the rep is told where to collect and deliver, records who handed the tyres over, and confirms delivery. Transfers now have a **delivery note** PDF and email (no prices; the other dealer is never named).
* **Sales journey:** each sale shows the stock track (replacement raised, shipped, delivered) and the billing track (invoice record, invoiced in Xero), plus the next step for you. The sales list shows **Invoiced?**, **Replacement**, **Xero no.** (RM, FM, Admin) and a **Not invoiced only** filter.
* **Stock checks:** choose the dealer, then the shop; the check shows the dealer, shop, address, city and rep. Tyres not found give the dealer **5 days**: **I found them, please re-check** or **Raise a dispute** (both pause the clock), or **Not found, invoice them now**. Staff can **Start re-count** or **Invoice the shortage**. When the 5 days end, the tyres are invoiced as sold automatically. Daily reminders meanwhile, and a contact card with names, emails and phone numbers (phone is a new optional field in Administration → Users).
* **Report by dealer, by SKU** (Reports): stock, on the way, waiting, sold, invoiced and not yet invoiced, per shop and tyre, with dealer totals and an **Excel** download. Units only.
* **Staff handover:** **Hand over…** moves a person's dealers, the deliveries and transfers they carry, and approvals waiting for them to a colleague with the same role. When adding a user you can say they **replace** someone (take over everything) or **work alongside** them (share chosen dealers). Nobody can be deactivated while things are still theirs.

### Changed
* **The Relationship Manager can do everything the Warehouse Manager can**, including purchasing, receiving, picking and shipping.
* **No prices or MRP on any screen, PDF or email.** Prices are set in Xero. The import template no longer has price columns (price columns in older files are ignored).
* **Check Stock** starts empty and searches only when you press **Search**. Request pages show stock for **only the tyres on that request**.
* **Change password** opens in a roomy dialog with show/hide buttons.
* **Invoices are invoice records:** create the invoice in Xero, then **Mark as invoiced in Xero** with its Xero number (required; can be corrected later, with a record of the change). The Xero number is shown only to the Relationship Manager, Finance Manager and Administrator; the Warehouse Manager and reps see **Invoiced ✓ / Not yet**; dealers see their invoice records without the Xero number.
* **"Cash sale (walk-in)" is now "Non-consignment sale (from warehouse)".** Same rules: stock leaves the warehouse, nothing is replaced, and its invoice record is completed in Xero.
* **Stock checks no longer have "Missing".** In consignment, tyres that aren't found are re-checked or invoiced. A stock-check invoice is an ordinary invoice record. (Counts from before 1.4.0 keep their old approve step.)
* UAT journey maps updated (Who's who with the Finance Manager; Journeys 1, 2, 3, 5, 6, 7, 8, 9, 11 and 12).
* Verification: 231 backend tests (79 new), 19 frontend unit tests (12 new), type check, lint, production build, 20 browser scenarios (13 new). Migrations 0011–0016 upgrade, downgrade and show no drift.

## 1.10.0 — Relationship Manager runs TyreGrow, new dashboards (2026-10-17)

**No database migration.** Merge and redeploy; nothing else to run.

### Changed
* **The Relationship Manager is now the administrator of TyreGrow.** They add and change user logins, reset passwords, read the change history (audit log) and tester feedback, and manage Settings, all from **Administration**.
* **The Warehouse Manager is no longer an administrator.** They keep all the warehouse work: stock, suppliers, picking and shipping, transfers. The **Administration** page is gone from their menu.
* **A dashboard for each role.** Each role now has its own layout, colour and to-do list:
  * **Relationship Manager — Owner's overview (blue):** money not yet invoiced, this month's sales, stock at dealers and in the warehouse, and what is waiting for supply. Then the decisions waiting for you, and how each dealer is doing this month.
  * **Warehouse Manager — Warehouse floor (amber):** on hand, available, reserved, blocked and incoming. Then today's jobs in order: approve, pick and ship, find tyres from dealers, collect transfers, receive supplier deliveries, deliveries on the road.
  * **Sales Rep — Field day (green):** my dealers, stock checks due, tyres to hand over, sales this month. Then today's visits, what is in your vehicle, and your dealers.
  * **Dealer — My shop (purple):** in my shop, on the way, waiting, sold this month. Then what to do next: confirm deliveries, ask for tyres running low, report sales.
  * **Administrator — System (grey):** users, products, stock, backorders and invoicing at a glance, plus the admin shortcuts.
* **Every number on a dashboard can be clicked** and opens the screen behind it. Dealers see plain numbers inside tables, as before.
* **Check stock button where you need it.** It now also appears on New transfer (for the chosen tyre), Create stock request, each stock request, Backorders, each replenishment request and each dealer's page. Dealers never see it.
* UAT journey maps updated (Who's who, Journeys 2 and 12).

## 1.9.0 — Clickable numbers and photo archiving (2026-10-15)

**Database migration:** `0010` (additive: archive and delete dates on photos, and a small settings table). Run **Database setup** (uat_reset and pilot_reset empty) after merging.
**One-time setup for the nightly clean-up:** add `CRON_SECRET` to the API project in Vercel and redeploy. See `docs/DEPLOY_VERCEL.md` → *Nightly photo clean-up*.

### New
* **Clickable numbers** on Warehouse, Stock Overview, Consignment Stock and each dealer's stock tab, including the top number tiles. Each number opens the screen that explains it, filtered to that tyre:
  * On hand (and blocked, shipped) → Stock Movement
  * Reserved → Stock Allocation (which dealer, which request)
  * Incoming → Purchasing (open orders)
  * Demand, open and unmet → Backorders
  * Available on Stock Overview → Check Stock
  * Delivered → Consignment Stock
  * Requested → Pending Approval

  A yellow **Showing…** bar with **Show all** removes the filter. Staff only; dealers see plain numbers as before.
* **Settings → Drop-off photo archiving** (Relationship Manager and Administrator). Photos are archived after a period you choose in days or months (default **6 months**). Archived photos disappear from normal screens; RM and Admin can still open them under **Archived photos**. Each archived photo is **deleted 90 days after it was archived**. Who received the stock and the notes are always kept, and the record shows "1 photo archived". A nightly job runs this automatically; **Run clean-up now** does it on demand.
* The UAT clean-up keeps this setting.
* UAT journey maps updated (Journey 11).
* Verification: 151 backend tests (4 new), 7 frontend unit tests, type check, lint, production build, 7 browser scenarios. Both new screens were checked in the browser.

## 1.8.0 — Check Stock, proof of receipt and drop-off photos (2026-10-15)

**Database migration:** `0009` (additive: "received by" on deliveries and transfers, receipt notes on transfers, and a new table for drop-off photos). Run **Database setup** (uat_reset and pilot_reset empty) after merging.

### New
* **Check Stock** (menu, plus a **Check stock** button on Replenishment, Stock Transfers and each transfer). Pick a tyre to see the main warehouse quantity and every dealer holding it: available, on hand, held back, and whether it can be transferred. For Administrators, Relationship Managers, Warehouse Managers and Sales Reps (view only). Dealers never see it.
* **Drop-off photo.** **Take photo** when confirming a delivery or transfer. The photo is shrunk on the phone to about 100–250 KB before upload; up to 3 photos per delivery. Photos show on the delivery or transfer, and the first one is printed on the delivery note PDF that is emailed to the dealer.

### Changed
* **Stock sent with a Sales Rep** (warehouse deliveries and stock-request shipments) can be confirmed **only by the receiving dealer or that Sales Rep**. Warehouse and Relationship Managers see "To be confirmed by the dealer or (rep)". Courier deliveries are unchanged.
* **Transfers:** the **receiving dealer** can now confirm receipt. If a Sales Rep collected the tyres, only that Sales Rep or the dealer can confirm.
* **When a Sales Rep confirms** any delivery or transfer, **Received by** (name) and **Hand-over notes** are required. Both show on the record and on the delivery note PDF and email.
* Unchanged and now spelled out in the UAT maps: a transfer never invoices the giving dealer, who gets an automatic replacement (backfill). The receiving dealer is invoiced only when they sell.
* UAT journey maps updated (Journeys 5, 6, 7 and 11).
* Verification: 147 backend tests (6 new), 7 frontend unit tests, type check, lint, production build, 7 browser scenarios. The photo flow was checked on a phone-sized screen.

## 1.7.1 — Clean-up for UAT (2026-10-12)

No database change.

* New **uat_reset** option in **Actions → Database setup**. `PREVIEW` lists what would be kept and deleted. `CLEAN-FOR-UAT` keeps user logins, dealers, dealer-specific prices, SKUs and tax rates, deletes all orders, stock and history (including dealer agreed stock levels), restarts document numbers, and puts 10 of every active SKU in the main warehouse. It never runs on its own. See `docs/DEPLOY_VERCEL.md`.
* Verification: dry run and clean-up run on a local copy of the test database (dealers, SKUs and logins unchanged; every SKU at 10 in the warehouse). All 7 browser scenarios passed on the cleaned database, and a new safety test checks the keep list.

## 1.7.0 — "Get this tyre for me" (2026-10-12)

**Database migration:** `0008` (additive: three columns on stock request lines). Run **Database setup** (no boxes ticked) after merging.

* When a dealer asks for a tyre the warehouse can't fully supply, a kind note appears under that line on **Create stock request** instead of any "out of stock" wording: **"Leave this one with us. We're arranging this tyre for you and will let you know as soon as it's on its way."** with a **Get this tyre for me** button. After clicking: *"Thank you! Our team is on it."* (with Undo). The dealer never sees warehouse stock figures.
* On submit, the part the warehouse can't supply goes straight to the **Warehouse Manager** (Relationship Manager copied) as a transfer request from another dealer, with a notification *"Please find … for …"*. The warehouse arranges it in the existing **Stock Transfers** screen: choose the dealer who holds it, record consent, collect, deliver.
* The Central Team approves only what the warehouse can supply. If the warehouse is arranging everything on the request, no approval is needed.
* The dealer gets *"Good news: … is on its way"* when the tyre is collected. If an arrangement is rejected or cancelled, the Warehouse and Relationship Managers are told the dealer is still waiting. The dealer is never sent a negative message.
* The order page shows the same warm note to the dealer; staff see "Being arranged from another dealer: 3 · TRF-…".
* Without the button, ordering works exactly as before.
* Verification: 140 backend tests (5 new), 7 frontend unit tests, type check, lint, production build, 7 browser scenarios, and the dealer journey checked in the browser on desktop and phone.

## 1.6.0 — "Where did this tyre come from?" (2026-10-11)

No database change; no Database setup run needed.

* A small **ⓘ** now sits next to each tyre in: the dealer's stock (Consignment stock), the dealer page's *Consignment stock by SKU*, *My stock requiring attention* on the dealer dashboard, Warehouse stock, replenishment requests and stock request lines.
* Hover over it (or tap it on a phone) for a two-line summary, e.g. **"2 tyres received on 15 Oct 2026 · DEL-000041 — Replacement for your sale SAL-000118."** It covers initial stock, Latest stock (new tyres), orders and who placed them, sale replacements, stock-check finds, transfers from another dealer and supplier deliveries.
* When today's stock came in more than one way, a third line shows the mix, e.g. *In stock now: 2 replacing sales · 4 initial stock*. **Show all arrivals** lists the last 12 months.
* Dealers see only their own stock; another dealer's name is never shown to them.
* Fast by design: nothing extra loads with the page. The summary is fetched only when someone opens an ⓘ and is remembered for a minute.
* Verification: 135 backend tests (2 new), 7 frontend unit tests, type check, lint, production build and 7 browser scenarios passed. About 6 small database queries per ⓘ opened (~18 ms locally).

## 1.5.1 — "Reseller" is now "Dealer" (2026-10-11)

No database change; no Database setup run needed.

* Every word people see now says **Dealer** instead of **Reseller**: menus, page titles, buttons, table headings, pop-ups, notifications, error messages, the delivery note PDF and email, and the role name.
* Nothing else changed. Web addresses (e.g. `/resellers/12`), internal codes, permissions, stored data and every journey stay the same.
* Verification: 133 backend tests and 7 browser scenarios passed. A scan of every main page for each role found no remaining "reseller" wording; only test data names contain it.

## 1.5.0 — Existing resellers, cash sales, shipping with sales reps, delivery notes (2026-10-10)

**Database migration:** `0007` (additive: new columns on sales, deliveries, replenishment requests and resellers). Run **Database setup** (no boxes ticked) after merging.
**New dependencies:** `fpdf2` (PDF delivery notes) and `tzdata`. Vercel installs them automatically.

### New
* **Initial stock (backorder)** for existing resellers. When you add a reseller, choose *Existing TyreGrow reseller* and enter the tyres they hold today. You can also add it later with **Initial stock** on the reseller's page (Relationship Manager, Warehouse Manager, Administrator).
* **Latest stock** label on orders for a tyre the reseller has never held.
* **My Sales** for resellers: tyres sold, value, by tyre and by day / week / month, for today, this week, this month, last month, this year or chosen dates.
* **Cash sale (walk-in)** in the Record sale pop-up: sells from warehouse stock, records the customer's name and phone, and creates a draft invoice (Relationship Manager, Warehouse Manager, Administrator).
* **Send with a sales representative** as well as by courier, for stock request shipments and Pick & dispatch. The rep is notified and confirms delivery.
* **Delivery note** PDF for every confirmed delivery, with an automatic email to the reseller once SMTP is set up (see `docs/DEPLOY_VERCEL.md`). Includes **Resend email** and **Delivery note (PDF)** buttons.

### Changed
* **Report sale** (menu and dashboard buttons) opens the sales list first; the pop-up opens from its button.
* **Pop-ups** no longer close when you click outside them.
* **Tyres are shown by model and size** with the SKU everywhere (tables, shipments, invoices, history, notifications).
* **Request Stock:** the line-notes box is removed.
* **Reseller profile:** details are laid out in one column, so long emails and addresses no longer overlap.

### Verification
* Backend: 133 tests passed (7 new).
* Frontend: lint, typecheck and unit tests passed; production build succeeded.
* End-to-end: 7 browser scenarios passed (new: existing reseller with initial stock, cash sale, sales-rep shipping and delivery note; My Sales checked in the reseller scenario).

## 1.4.0 — Sale replacements, stock-check confirmation, who to invoice (2026-10-07)

**Database migration:** `0006` (additive: new columns on `stocktakes` and `stocktake_lines`). Run **Database setup** (no boxes ticked) after merging and before using stock checks.

### New and changed
* **Every sale raises a replacement** for the same tyre and quantity, including sales a reseller reports. Previously this needed a target level.
  * If a target is set, the replacement never goes above it.
  * Tyres with auto-replenish switched off are skipped.
  * The replacement is reserved and appears on the Warehouse Manager's pick list.
  * The Warehouse Manager, Relationship Manager and the reseller's Sales Rep are notified.
  * Replenishment lists and details show **Raised by** (name and role).
* **Stock checks: the reseller confirms missing tyres.** When the Sales Rep's count is short:
  * The missing quantity is held, and the reseller confirms each shortage as **sold** or **missing**.
  * Sold tyres become a sale, a replacement and a **draft invoice**.
  * Missing tyres are written off.
  * Staff can confirm on the reseller's behalf, with a reason.
  * Unconfirmed checks send repeating reminders to the reseller, the Sales Rep and the Warehouse Manager. They are highlighted on the reseller, Warehouse Manager and Relationship Manager dashboards.
  * Counts with no shortage post immediately.
* **Who to invoice:** the invoices page lists, per reseller, the tyres sold and not invoiced (units, by SKU, value, oldest), with one-click selection for a draft invoice.

### Configuration
* `STOCKTAKE_CONFIRM_HOURS` (default 48) and `STOCKTAKE_REMINDER_HOURS` (default 24).

### Verification
* Backend: 126 tests passed. Tests for the replaced rules (no replacement without a target; staff approval of shortages) were rewritten for the new rules, and new tests cover reminders, on-behalf confirmation and cancellation.
* Frontend: lint, typecheck and unit tests passed; production build succeeded.
* End-to-end: 6 browser scenarios passed, including the new stock-check scenario.

## 1.3.0 — Stock allocation & consignment requests (2026-10-05)

**Database migration:** `0005` (additive: four new tables and six new nullable columns on `deliveries`). Run `alembic upgrade head`, or the **DB setup** workflow, before using the new screens. No existing data is changed or removed.

### New
* **Consignment stock requests.** Multi-SKU requests go through draft → submitted → under review → approved / partially approved / rejected → ready for shipment → shipped → delivered.
  * Sales Reps can request on behalf of any reseller; the requester and their role are recorded.
  * Resellers request for their own account.
* **Central Team approval** by the Relationship Manager, Warehouse Manager or Administrator.
  * Approval is line by line, showing requested, approved, backordered and rejected quantities.
  * Approved stock is reserved immediately, so it cannot be allocated twice.
  * Backorders can be reserved later; reservations can be released.
* **Shipments** record carrier, tracking number, shipping address and notes. **Delivery confirmation** records date, reference, quantities and notes; resellers can now confirm their own deliveries.
* **Inventory views:**
  * Stock Overview (Total, Available, Reserved, Shipped, Delivered).
  * Stock Allocation (what is reserved, for whom).
  * Stock Movement (the ledger).
* **In-app notifications** via a bell in the top bar, with an unread count.
* **Dashboards:** every role gets a consignment request panel (pending approval, to ship, in transit, delivered, recent requests).
* **Full history and audit trail** per request: user, role, action, quantities and status change.
* **Configurable limits:** `STOCK_REQUEST_MAX_LINES` (default 50) and `STOCK_REQUEST_MAX_LINE_QTY` (default 500).

### Changed (confirmed before implementation)
* **Approval gate.** Quick replenishment requests raised by a Reseller or Sales Rep no longer auto-reserve warehouse stock; staff allocate them. Staff requests and sale- or transfer-triggered replenishment behave as before.
* **Navigation:** new Consignment and Inventory menu entries. The reseller's "Request Replenishment" menu item and dashboard button now open **Request Stock**. The old replenishment request form still works from Backorders.
* **Reseller permissions** now include `stock_request.read`, `stock_request.create` and `delivery.confirm`, scoped to their own account.
* **Deliveries API** also returns tracking number, shipping address, linked stock request, delivery date, reference and receipt notes. These fields are additive and optional.
* **"Coming later"** no longer lists Notifications or Excel product import.

### Fixed
* The product picker's filter box no longer squeezes the product dropdown to a sliver on wide forms.

### Verification
* Backend: 122 tests passed (116 existing + 6 new). One existing permission-matrix assertion was updated for the new reseller permissions.
* Frontend: lint, typecheck and 7 unit tests passed; production build succeeded.
* End-to-end: 5 browser scenarios passed (4 existing + new "consignment stock request" scenario).

## 1.2.0 — Administrator super user, Excel product import, RRP
## 1.1.0 — Pilot preparation (four roles, clean state, feedback)
## 1.0.0 — Consignment platform and UI redesign
