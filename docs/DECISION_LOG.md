# TyreGrow — Decision Log

Format: **ID — Decision.** Context / rationale. *Status.* "Assumption" entries need dealership validation (BC §16).

## Technical decisions

**D-001 — Modular monolith: FastAPI + SQLAlchemy 2 (sync) + PostgreSQL; Next.js frontend.** The preferred stack from the instructions. Sync SQLAlchemy makes transaction and lock scope explicit, which matters more here than async throughput. *Accepted.*

**D-002 — Double-entry inventory ledger with virtual locations.** Every physical movement is from one location to another, including virtual SUPPLIER, SOLD, ADJUSTMENT, OPENING and SCRAP locations. Stock is conserved by construction and "the same tyre in two places" becomes structurally impossible. *Accepted.*

**D-003 — Reserved and blocked are sub-states of on-hand, tracked as ledger buckets.** Reservation and block events are ledger entries in their own buckets, so all three balances can be rebuilt from history. *Accepted.*

**D-004 — A single `TRANSIT` location.** In-transit stock is attributed to documents (delivery lines, transfers) rather than to per-trip locations. This keeps the location list small while the per-document quantities stay reportable. *Accepted.*

**D-005 — Balance projection plus DB check constraints plus row locks.** `stock_balances` is updated in the same DB transaction as the entries. `FOR UPDATE` in a deterministic lock order handles concurrency, and check constraints are the backstop. *Accepted.*

**D-006 — One replenishment request entity; "backorder" is a derived view.** A backorder is the awaiting-supply part of a request (`outstanding − allocated − in_transit`). This avoids two records for one obligation, and still lets reports distinguish allocated stock from quantity awaiting supply (BC §11.2). *Accepted.*

**D-007 — Integer primary keys plus human-readable document numbers** (for example `SAL-000001`, `REP-000001`, `TRF-000001`, `DEL-000001`, `INV-000001`) from a locked `number_sequences` table. Prefixes are neutral (no brand). *Accepted.*

**D-008 — Session cookie via same-origin proxy.** Next.js rewrites `/api/*` to FastAPI. The JWT is stored in an httpOnly SameSite=Strict cookie. Bearer tokens are also accepted for API clients and tests. *Accepted.*

**D-009 — One role per user.** Simple and adequate for the six defined roles. Permissions are defined per role in code (`core/permissions.py`), so they are reviewable and testable. *Accepted; revisit if custom roles are needed.*

**D-010 — Tests run against real PostgreSQL** (database `tyreworld_test`), because locking and constraints are part of the behaviour under test. *Accepted.*

**D-011 — Transfers are single-SKU documents.** The business case describes transfers per SKU and quantity. Sales, purchase orders, goods receipts and deliveries are multi-line. *Accepted for MVP.*

**D-012 — No separate "picking" state in the MVP.** Allocated → Dispatched. A printable pick list is derived from active allocations. *Accepted for MVP.*

**D-013 — Transfer counterparty is hidden from reseller users.** Resellers see that stock left or arrived via a transfer, but not which other reseller was involved (MI §5: no access to another reseller's data). Staff see both parties. *Accepted.*

**D-014 — Client-rendered frontend over a same-origin API.** Pages are React client components that call the API through the `/api` rewrite. Authorisation lives entirely in the backend; the UI hides actions the user lacks permission for, as a convenience only. *Accepted.*

**D-015 — Money serialised as decimal strings.** All monetary values leave the API as strings (never floats), including the untyped report endpoints. *Accepted.*

**D-016 — Single transaction per HTTP request.** Services never commit. Each router commits once, so a sale, its ledger entries, its replenishment request and its warehouse reservation succeed or fail together. *Accepted.*

## Business assumptions (pending dealership validation)

**A-001 — Replenishment on sale is capped by the target.** Sale-triggered demand = `min(sold qty, target − (on_hand + open demand + inbound transfers))`. It is disabled per allocation via `auto_replenish` (BC §16: "whether every sale requires replacement"). No allocation means no automatic replenishment.

**A-002 — Warehouse allocation is attempted immediately when demand is created** (`AUTO_ALLOCATE_ON_CREATE=true`). Goods receipts are **not** auto-allocated: the system proposes allocations by `PRIORITY_THEN_OLDEST`, and a user confirms them (BC §10).

**A-003 — The transfer-replenishment obligation is created at collection, not approval.** The source reseller is only owed stock once stock has physically left, so cancelling before collection leaves no orphaned obligation (MI Test 7).

**A-004 — Tyres lost in transit on a transfer do not remove the source obligation.** The source's allocation is still to be restored. The loss is posted as an approved adjustment.

**A-005 — Transfer consent is configured on the consignment agreement**: `PRE_AUTHORISED`, `PER_TRANSFER` (consent reference required at approval) or `NOT_ALLOWED`. Default: `PER_TRANSFER`.

**A-006 — The sale price is the effective customer-specific price, otherwise the product list price.** It is snapshotted on the sale line when the sale is recorded, and again on the invoice line.

**A-007 — Tax.** Rates live in a `tax_rates` table. The default rate is flagged `is_default`, and a reseller may have an override (for example exempt). The pilot reset creates one default rate from configuration (default "GST 15%", NZ); change it with `PILOT_TAX_*` or under Administration → Tax rates. Prices are treated as tax-exclusive.

**A-008 — Currency is a single configured code** (`DEFAULT_CURRENCY`, example value `AUD` in `.env.example`). The business case does not state a country. Change it per deployment.

**A-009 — Invoices are created on demand from uninvoiced sale lines** (per reseller, selectable), Draft → Issued. Invoice timing (per sale or periodic) is pending (BC §16). Void releases the sale lines for re-invoicing. Credit notes are deferred.

**A-010 — Only uninvoiced sales can be reversed in the MVP.** Invoiced sales need a credit-note workflow (deferred).

**A-011 — A stocktake shortage must be explicitly classified** as sold or missing. Missing stock is posted to ADJUSTMENT as a loss on approval, never as a sale. A surplus is posted as a gain. Approval needs `stocktake.approve`.

**A-012 — Reseller users are read-only in the MVP** (their own stock, demand, sales, invoices and history). Self-service actions are BC Phase 2.

**A-013 — On hold / closed resellers.** A reseller that is not `ACTIVE` cannot receive replenishment dispatches, is never auto-allocated warehouse stock, and cannot be a transfer source or destination. Sales can still be recorded for an `ON_HOLD` reseller, because they are chargeable facts; they are blocked for `CLOSED` accounts. Existing obligations remain visible. The account-closure procedure is pending (BC §16).

**A-014 — Priority** is `URGENT`, `HIGH`, `NORMAL` (default) or `LOW`. Changes need a reason and are audited.

**A-015 — Stocktakes are full counts of the location.** Stocked SKUs that were not counted are added with a count of zero when the stocktake is submitted, so every shortage must be explained. Approval is refused if stock moved after submission (recount).

**A-016 — Goods receipts may be recorded without a purchase order** (for example, an unplanned supplier delivery). Over-receipt against a PO line is rejected.

## Pilot decisions (October 2026)

**P-001: Four business roles.** The roles are Relationship Manager (the former dealership manager, plus invoicing), Warehouse Manager (stock, supply, product master, and user administration for the pilot), Sales Representative and Reseller. There is no separate administrator or finance role for the pilot.

**P-002: Reseller self-service.** Reseller users may report their own sales (always at the agreed price, source "Reported by reseller") and request replenishment for their own locations. A request must stay within the uncovered target shortfall and cannot be marked urgent. Everything else stays read-only and scoped to their own reseller.

**P-003: Price list is a reference, not data.** The dealer price list image (effective 7 July 2026) is served by the authenticated API to staff only. It never creates products, prices or stock. The Excel product master, to be supplied later, will be imported as products only. Stock stays 0 until it is received or posted.

**P-004: Clean start.** All demo data and the demo seed were removed. The one-time `reset_to_pilot` creates only the accounts, one warehouse and one tax rate. Deployments and migrations never delete pilot data.

**P-005: Navigation vs. access.** The Relationship Manager also gets Products (read-only catalogue and the price list), and the Warehouse Manager also gets Stocktakes & Sales and Administration. Both are needed to operate the pilot, though they were not in the proposed menus.

**P-006: Administrator super user.** One Administrator role has every permission, so a single person can manage the whole pilot. Only an Administrator may create, promote to or change an Administrator account. The Relationship Manager can manage users but cannot escalate to Administrator (see P-027). The default password comes from a GitHub secret, never from Git, and must be changed at first sign-in.

**P-007: Excel product master.** One standard template defines the columns (`docs/templates/TyreGrow_SKU_Import_Template.xlsx`). Imports are checked first, then applied in one transaction.
- New SKU codes are created; existing ones have their description and prices updated.
- Tyre size is never changed by an import.
- Error rows are skipped and listed.
- "Dealer price" maps to the product's list price (the reseller price used for sales). RRP is stored for reference.
- Imports create products only, never stock.

## Stock allocation & consignment requests (October 2026, v1.3.0)

**P-008: Approval gate for requested stock.** Stock requested by resellers and sales representatives reserves nothing until the Central Team decides. This covers new consignment stock requests and the existing quick replenishment request. Replenishment triggered automatically by a sale or transfer, and requests raised by staff, keep the configured auto-allocation (`AUTO_ALLOCATE_ON_CREATE`).

**P-009: Stock requests extend replenishment.** They are not a parallel module. A consignment stock request is a multi-SKU header with an approval stage. On approval, each line with approved or backordered quantity becomes one replenishment request (reason `STOCK_REQUEST`). The approved quantity is reserved in the warehouse immediately, through the ledger. Shipment and delivery reuse replenishment dispatch and receipt, so demand is never double-counted and the existing Backorders, Replenishment and Pick & dispatch screens keep working. The stock request status is derived from those replenishment quantities.

**P-010: Central Team = Relationship Manager + Warehouse Manager + Administrator.** All three may review, approve, partially approve, reject, reserve backorders and release reservations. Only the Warehouse Manager (and the Administrator) marks requests ready and ships. The Relationship Manager still cannot receive or adjust physical stock.

**P-011: Sales representatives keep seeing all resellers.** They can raise requests on behalf of any reseller; the requester and their role are recorded. They cannot approve. Resellers remain isolated to their own account.

**P-012: Partial approval.** For each line the approver chooses whether the unapproved remainder is **backordered** (it waits for supply and is reserved later, either from the request or from the Backorders allocation proposal) or **rejected**. Approved quantity can never exceed the warehouse's available quantity.

**P-013: Resellers confirm their own deliveries.** They do this alongside staff, recording the delivery date, a reference and quantities. Short quantities stay in transit until the warehouse resolves them (returned, lost or late).

**P-014: Inventory formula.** In the stock overview, Total = warehouse on hand + shipped (in transit), and Available = Total − Reserved − Shipped − Blocked. This equals the ledger's warehouse available. Delivered stock is the resellers' consignment on hand. The ledger itself is unchanged.

**P-015: Notifications are in-app only.** A bell in the top bar shows notifications for submission, review, decision, ready, shipped, delivered and released events. Email is deferred.

**P-016: Configured limits.** `STOCK_REQUEST_MAX_LINES` (default 50 SKUs per request) and `STOCK_REQUEST_MAX_LINE_QTY` (default 500 per SKU).

## Sales replacements, stock-check confirmation and invoicing view (October 2026, v1.4.0)

**P-017: Every sale replaces the same tyre.** A confirmed sale raises a replacement request for the same SKU and the quantity sold. This replaces A-001's rule that no replacement is raised without a target.
- If an active target is set, the replacement is capped at the uncovered shortfall, so stock never goes above target.
- If auto-replenish is switched off for that SKU, no replacement is raised.
- The replacement follows the normal journey: reserve, pick and dispatch, then reseller receipt.
- The Warehouse Manager, the Relationship Manager and the reseller's sales rep are notified in-app. The request shows who raised it ("Raised by"; for a reseller-reported sale, the reseller user). Resellers can still request extra stock themselves through Request Stock.

**P-018: Stock-check shortages are confirmed by the reseller.** This replaces staff classification and approval (A-011) for new counts.
- **Submission.** The Sales Rep records and submits the count. If nothing is short, the result (surpluses, damaged stock) posts immediately.
- **Hold.** If tyres are short, the shortage quantity is held (blocked) and the reseller is notified. They must confirm each shortage as **sold** or **missing**; nothing is assumed.
- **Sold.** Sold quantities become a confirmed sale, which raises a replacement (P-017) and a **draft** invoice that the Relationship Manager reviews and issues.
- **Missing.** Missing quantities are posted as an approved loss.
- **On-behalf confirmation.** A Relationship Manager, Warehouse Manager or Administrator may confirm on the reseller's behalf, but must give a reason, which is recorded and audited.
- **Reminders.** A confirmation is due `STOCKTAKE_CONFIRM_HOURS` (default 48) after submission. After that, reminders go to the reseller, the counting and assigned sales rep, and the Warehouse Managers, and repeat every `STOCKTAKE_REMINDER_HOURS` (default 24) until it is confirmed. Reminders are generated when users' notification bells refresh, so no scheduler is needed.
- **Visibility.** Open and overdue checks are highlighted on the reseller, Warehouse Manager and Relationship Manager dashboards.
- **Cancelling** a count releases the hold.
- **Older counts.** Counts submitted before this release (status SUBMITTED) keep the old staff approval.

**P-019: Who to invoice.** The invoices page opens with a per-reseller summary of tyres sold and not yet invoiced: units, by SKU, net value and oldest sale. One click selects that reseller's lines for a draft invoice. The dashboard's "Sales awaiting invoice" tile leads there.

## Onboarding existing resellers, cash sales, shipping and delivery notes (October 2026, v1.5.0)

**P-020: Initial stock (backorder).** When an existing TyreGrow reseller is added, the tyres they already hold are recorded once as their **Initial stock (backorder)**. This posts the stock to their consignment location through the ledger's opening-balance account. A Relationship Manager, Warehouse Manager or Administrator enters it from the add-reseller form (choose "Existing TyreGrow reseller") or from the reseller's page.

**P-021: Latest stock.** A replenishment request for a tyre the reseller location has never held is flagged **Latest stock**. Everything else stays replenishment.

**P-022: Pop-ups close only with their own buttons** (Back, Cancel or ×); clicking outside never closes them. Esc still closes them, for keyboard users.

**P-023: Cash sales.** A walk-in customer (a nearby shop or any reseller) can buy at the warehouse.
- "Cash sale (walk-in)" is the first option in the Record sale pop-up for the Relationship Manager, Warehouse Manager and Administrator.
- Stock leaves the default warehouse, priced at the dealer price (overrides need a reason).
- No replacement is raised.
- A **draft** invoice is created for the customer's name and grouped under a hidden system account, "Cash sales (walk-in)". That account is not listed among resellers.

**P-024: Shipping with a sales representative.** Shipments travel either by **Courier** (carrier and tracking number) or with a **Sales representative**, who is notified and confirms delivery at handover.

**P-025: Delivery notes.** Every confirmed delivery has a standard PDF delivery note: tyres, quantities, delivery date and time, and the 14-day discrepancy notice. When SMTP is configured, it is emailed automatically to the reseller's email address on confirmation, and staff can resend it. Until SMTP is set up, nothing is emailed and the PDF can be downloaded.

**P-026: Tyres are named by model and size** wherever a SKU appears, with the SKU alongside.

**P-027: The Relationship Manager administers TyreGrow (v1.10.0).** The Relationship Manager is the head of TyreGrow, so user logins, the audit log, pilot feedback review and settings move from the Warehouse Manager to the Relationship Manager. The Warehouse Manager keeps full operational authority but is no longer an administrator and loses the Administration page. This supersedes the user-administration part of P-001 and P-005. Each role now has its own dashboard layout (owner's overview, warehouse floor, field day, my shop, system), and every number on a dashboard opens the screen behind it.

**P-028: The Relationship Manager sits above the Warehouse Manager (v1.11.0).** The RM's permissions are built from the WM's set plus the RM-only ones (dealers, prices, sales, invoicing, administration), so the RM can also buy and receive stock, adjust, block and write off, edit products, pick, dispatch and ship. Warehouse notifications ("approved — ready to pick") still go only to Warehouse Managers and Administrators, so RMs are not flooded with warehouse work.

**P-029: Finance Manager role (v1.11.0, decision D1).** A Finance Manager handles billing: invoice records, marking them invoiced in Xero and the Xero numbers, with read-only sales, dealers and reports, and no stock actions. Their permissions are a subset of the RM's. A new permission, `invoice.reference_read`, controls who sees invoice and Xero numbers on sales (RM, FM, Administrator). A Finance Manager is never offered as a sales representative.


**P-030: No prices on any screen (v1.11.0, D2).** Prices and MRP are set in Xero. They are removed from every screen, PDF and email, and nothing requires a price any more. A sale with no agreed price is recorded as "not priced" (0.00). The price columns stay in the database and the API (additive rule) and the import template ignores them. The dealer price-list image is hidden.

**P-031: Account references are generated (v1.11.0, D4).** A new dealer's account reference is three letters from the business name, three from the city and a three-digit number (for example AKT-AUC-001). It is shown on the form and cannot be typed. Existing dealers keep theirs. Each shop gets the dealer's reference plus -01, -02, …. Phone, email, billing address and sales rep are required for new dealers.

**P-032: The dealer's login is created with the dealer (v1.11.0, D7).** On the New dealer form, "Create their login" makes a dealer user with a temporary password. The password is shown once, with a Copy button, and is never emailed. The dealer chooses their own at first sign-in.

**P-033: Agreement copies (v1.11.0, D8).** A copy of the signed consignment agreement can be attached to a dealer: PDF, JPG, PNG or WEBP, up to 5 MB each. Copies are stored in the database and are visible to dealership staff.

**P-034: Approval details are recorded (v1.11.0, finding 17).** Approving a stock request or a replenishment request records who approved it (the signed-in user), how (phone, in person, email, text or standard approval), who they spoke to (not needed for a standard approval) and comments. These are visible to staff only.

**P-035: A Warehouse Manager can send an approval to a Relationship Manager (v1.11.0, D10).** While it waits, only that Relationship Manager (or an Administrator) can approve or reject it. They can also hand it back to the warehouse. After approval the warehouse carries on as usual. Replenishment approvals use a new permission, `replenishment.approve` (Warehouse Manager, Relationship Manager, Administrator), because Sales Reps manage replenishment requests but do not approve them.

**P-036: Kind message to dealers (v1.11.0, D5).** Whenever any part of a dealer's order cannot be supplied, the dealer sees: "Sorry, we couldn't deliver your order this time, but we're working on it. Please feel free to call us, or let us know when we can call you." The internal reason stays with the staff. "Please call me" lets the dealer or the rep ask for a call; the Relationship Managers and the dealer's rep are told.

**P-037: Replenishment requests have their own fulfilment (v1.11.0, finding 22).** A request raised by a dealer or rep waits for approval; staff and system requests behave as before. A replacement after a sale or transfer that reserved stock by itself shows as "Approved automatically". Lines created by a stock request are approved, shipped and delivered on that stock request, not on the replenishment request.

**P-038: Transfers are carried by a sales rep or a courier (v1.11.0, finding 23).** When a rep is assigned, only that rep (or an Administrator) records the collection, saying who handed the tyres over, and only that rep or the receiving dealer confirms the delivery. Older transfers with nothing arranged keep the earlier rule. The transfer delivery note goes to the receiving dealer and never names the other dealer.

**P-039: Invoice records are completed in Xero (v1.11.0, finding 24).** The app's invoice is an invoice record: the sold tyres to bill. Someone creates the invoice in Xero, then marks the record "Invoiced in Xero" with the Xero number, which is required. The number can be corrected later, and the change is recorded.

**P-040: Who sees invoice and Xero numbers (v1.11.0, D12).** Everyone who can see a sale sees whether it is invoiced. The invoice record number goes to the Relationship Manager, Finance Manager, Administrator and the dealer (their own). The Xero number goes only to the Relationship Manager, Finance Manager and Administrator. The Warehouse Manager and reps see "Invoiced ✓ / Not yet".

**P-041: Non-consignment sales (v1.11.0, D6).** "Cash sale (walk-in)" is renamed "Non-consignment sale (from warehouse)". This is a label only: the code stays CASH_SALE and the rules of P-023 are unchanged, except that its invoice record is completed in Xero like any other (P-039).

**P-042: Stock checks: tyres not found are re-checked or invoiced (v1.11.0, D3, findings 28–30).** Nothing is written off as "missing" from a dealer's stock check. The dealer has `STOCKTAKE_FIND_DAYS` (5 calendar days) to find tyres not found. They can ask for a re-check (a rep or the warehouse starts a re-count; the original is marked superseded and its hold is released), raise a dispute for the Warehouse and Relationship Managers, or have them invoiced now. Re-check and dispute pause the clock. When the days run out, TyreGrow invoices the tyres as sold automatically: a sale, an invoice record and a replacement, recorded as "Automatically invoiced: not found within 5 days". Reminders go out daily meanwhile. The stock-check invoice is an ordinary invoice record. Counts from before P-018 (status SUBMITTED) keep their old classify-and-approve step, including "missing".

**P-043: Report by dealer, by SKU (v1.11.0, finding 31).** Per shop and tyre: on hand, available, held, on the way, waiting, and sold, invoiced and not yet invoiced in the chosen period. Units only. "Invoiced" means the sold tyres whose invoice record is marked invoiced in Xero, so sold = invoiced + not yet invoiced. Dealers see only their own.

**P-044: Staff handover (v1.11.0, D9).** A person's dealers, the deliveries and transfers they are carrying, and approvals waiting for them can be handed to a colleague with the same role, all at once or for chosen dealers. A new user can be added as replacing someone (take over everything and deactivate them) or as working alongside them. Nobody can be deactivated while any of these are still theirs ("Hand them over first"), so no dealer is ever left without a rep.

**P-045: Notifications pop up (v1.11.0, D11).** New notifications show as pop-ups with a short sound (on by default, switch off per user), the unread count in the browser tab, and optional desktop alerts. One poll every 20 seconds also drives the stock-check reminders and the end of the find window.

**P-046: Correcting a dealer's initial stock (UAT).** Initial stock is sometimes entered wrongly while onboarding a dealer. The Relationship Manager (and the Administrator) can correct it with a reason; nobody else, not the Warehouse Manager. The original entry is kept and a correction transaction points at it (INVENTORY_RULES §8), so audits can always see what was entered, what it became, who changed it and why. Only free stock can be taken out, corrections stop at the first stock check or after 30 days (`INITIAL_STOCK_CORRECTION_DAYS`), they are never invoiced, and Administrators and Finance Managers are told about each one. Reports → Stock corrections lists them all.

**P-047: Sign-in protection (UAT round 2).** Passwords: 10 characters minimum, 72 bytes maximum (bcrypt's limit; refused with a plain message instead of failing), any characters, no complexity rules (length matters most). 5 wrong passwords in a row lock the account for 15 minutes; RM/Administrator can unlock, and setting a password unlocks. The current and two previous passwords can't be reused.

**P-048: Dealer name first (UAT round 2).** People identify a dealer by business name, not by code or address. Every shop label leads with the dealer name, then the shop and city; the code is secondary (kept at the end of picker options to tell shops apart). Addresses only on delivery documents.

**P-049: A new dealer's first stock goes through the warehouse (UAT round 2).** A dealer is recorded as new or existing when added (`joined_with_stock`). A new dealer's stock comes through a stock request (approval, picking, delivery by the Sales Rep); initial stock is only for an existing dealer who already holds TyreGrow stock.

**P-050: Transfer route and shortfalls arranged at approval (UAT round 2).** The Warehouse Manager chooses, per transfer, direct or via the warehouse (received and checked there before delivery; the stock stays in transit). The rest of a stock request line can be arranged from another dealer at approval: backordered and covered by a linked transfer request.

**P-051: Stock check schedule (UAT round 2).** Each shop is due 30 days after its last count. The Sales Rep (own dealers), Warehouse Manager or Relationship Manager can move a check up to 14 days ahead with a reason. The rep is reminded on the day; the Warehouse and Relationship Managers are alerted weekly while a shop is overdue.
