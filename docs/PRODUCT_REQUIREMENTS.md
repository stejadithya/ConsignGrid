# TyreGrow — Product Requirements

Source: `docs/reference/Tyre_Consignment_Management_Business_Case.pdf` (v1.0, 29 Sep 2026, "proposed scope for dealership review") plus the master development instructions.

Every item below is tagged:

- **[BC §n]** — stated in the business case, section *n*.
- **[MI]** — stated in the master development instructions.
- **[ASSUMPTION]** — our reasonable interpretation, pending dealership validation. All assumptions are also listed in `DECISION_LOG.md`, and are configurable where practical.

## 1. Purpose

TyreGrow is a B2B consignment inventory platform for a tyre dealership with one central warehouse and 30+ reseller customers [BC §1]. It provides a single, auditable view of stock ownership and location, confirmed sales, invoice status, outstanding replenishment, transfers, incoming shipments and reseller-level transactions [BC §1].

Core design principle: **sales, invoices, physical movements, replenishment and backorder obligations are separate but linked business events** [BC §17, §2].

## 2. Actors and terminology [BC §2, MI §1]

| Term | Meaning |
|---|---|
| Dealership | Wholesale distributor; owns consignment stock; invoices resellers for sold goods. |
| Reseller (Customer) | Business holding dealership-owned stock at one or more consignment locations. |
| End customer | Consumer buying from a reseller. Not an account in this system. |
| Warehouse | Dealership location that receives supplier shipments and fulfils replenishment. |
| Consignment location | Reseller premises holding unsold dealership-owned stock. |
| Sales representative | Dealership employee who performs stocktakes, records sales and supports replenishment. |

## 3. Business scenarios (must work end to end in the first release) [BC §5–7, §14]

### S1 — Standard replenishment, warehouse stock available [BC §5]
1. Record the sale (reported by reseller or confirmed by stocktake).
2. Reduce the reseller's unsold consignment stock.
3. The sale becomes invoiceable at the reseller's commercial terms.
4. Create a linked replenishment request, bounded by the agreed target and existing open requests.
5. Check warehouse availability; reserve; dispatch.
6. Confirm delivery; update balances; close the fulfilled request.
- Replenishment delivery never creates an invoice. Partial fulfilment supported. Reservations prevent over-allocation.

### S2 — Warehouse stockout: sale + backorder [BC §6]
- Sale is confirmed and invoiceable regardless of warehouse availability.
- Unallocatable quantity remains as an open backorder carrying reseller, SKU, quantity, originating sale, priority and expected shipment date (if known).
- An expected shipment is not on-hand stock. A goods receipt alone never closes a backorder — only delivery of the full quantity or an authorised resolution does.
- Receipts are **proposed** for allocation by a configurable policy, not assigned blindly [BC §10].
- Authorised staff may change priority, with a reason recorded.

### S3 — Inter-reseller transfer of unsold stock [BC §7]
- Raise an urgent requirement at the destination reseller.
- Search consignment locations for the **exact SKU** with available (unsold, unreserved, unblocked) stock.
- Select source; record dealership approval and source-reseller consent.
- Reserve at source → collect (in transit) → destination acknowledges receipt.
- Total unsold dealership-owned inventory is unchanged by a transfer.
- Create a linked replenishment obligation for the source reseller.
- **A transfer is not a sale.** Neither reseller is invoiced because of the transfer; the destination is invoiced only on a later sale.
- Cancellation after collection requires an explicit reversal (return) or onward movement record.

## 4. Functional requirements by module

### 4.1 Product catalogue [BC §4, §12; MI §4A]
- Unique SKU, brand, pattern, width / aspect ratio / rim diameter, load index, speed rating, description, barcode, cost and list price (cost visible only to authorised roles), active flag.
- Products with similar dimensions are never treated as interchangeable. All matching is by exact product.
- Batch or manufacturing date (DOT) tracking: **deferred** (BC §12 says "where required").

### 4.2 Resellers, locations, agreements [BC §4, §13; MI §4B]
- Profile: business name, account reference, contacts, billing address, assigned sales rep, payment terms, tax treatment, status (Active / On hold / Closed).
- Multiple physical locations per reseller.
- Consignment agreement: reference, dates, transfer-consent rule, default auto-replenish flag.
- Customer-specific prices, with effective-from dates.

### 4.3 Consignment allocations [BC §12; MI §4C]
- Target quantity (plus optional min and max) per reseller location and SKU; target changes are audited with a reason.
- Views: target, on hand, available, open replenishment, inbound (in transit), remaining unmet requirement.
- Never create replenishment demand for a shortfall that open demand already covers [BC §9].

### 4.4 Warehouse [BC §4; MI §4D]
- Opening inventory, supplier receipts (optionally against a purchase order), reservations, dispatch, adjustments, damaged/blocked stock, location-level visibility.

### 4.5 Consignment sales [MI §4E]
- Multi-line sale per reseller location: sale date, quantity, agreed unit price snapshot, tax snapshot, source (reseller report / stocktake / rep visit), source reference, invoice status.
- Correction by controlled reversal (uninvoiced lines only in the MVP; invoiced lines need a credit note, which is deferred).

### 4.6 Replenishment & backorders [BC §8, §10; MI §4F]
- One demand record type, the **replenishment request**, with a reason: `SALE`, `TRANSFER`, `TARGET_SHORTFALL` or `MANUAL`. "Backorder" is the portion of a request still awaiting supply (see `INVENTORY_RULES.md`).
- Fields: unique number, reseller/location, SKU, originating transaction and type, required / allocated / in-transit / delivered / cancelled quantities, priority, expected date, supply reference (PO line), status, notes.
- Statuses: Open, Partially Fulfilled, Allocated, In Transit, Fulfilled, Cancelled [BC §10]. Quantities are always shown alongside the status.
- Each partial fulfilment is recorded individually (allocation rows, delivery lines).
- Cancellation needs a permission and a reason.
- A reseller's consolidated shortage is presented as a total, while sales-driven and transfer-driven histories stay separate [BC §8].

### 4.7 Inter-reseller transfers [BC §7; MI §4G]
- Lifecycle: Requested → Approved (source reserved) → In Transit (collected) → Received / Received with discrepancy → Completed; or Cancelled / Rejected.
- Discrepancy resolution: return to source, write off as lost, or late delivery. Every resolution records a user, reason and time.
- May optionally fulfil an existing destination replenishment request.

### 4.8 Stocktakes [BC §12; MI §4H]
- Expected vs counted quantity per SKU, counted-damaged quantity, count date, operator.
- Each shortage must be classified as **sold** or **unexplained/missing** before approval. Missing is never assumed sold.
- Approval (separate permission) posts: a sale for the sold quantity, a block for damaged stock, and adjustments for unexplained differences.

### 4.9 Purchasing & incoming supply [BC §4, §10]
- Purchase orders with lines, expected date and supplier reference. Receipts against PO lines (or ad hoc), with an accepted vs damaged split.
- Incoming quantities are never counted as on-hand.
- Allocation proposal for open backorders using a configurable policy (priority, then oldest), which a user confirms.

### 4.10 Invoicing [BC §4, §9; MI §4I]
- Invoices are built from confirmed, uninvoiced sale lines. Draft → Issued → (Void with reason).
- The database guarantees no duplicate invoicing of a sale line.
- Financial snapshot (SKU, description, price, tax code and rate, totals, billing details) is stored on the invoice.
- Tax rates are configurable data, never hard-coded. Currency comes from configuration.
- Accounting integration boundary: an export interface plus an external-reference field. The MVP includes a printable invoice view.

### 4.11 Reporting [BC §11; MI §4J]
Mandatory:
1. **Total consignment stock** — unsold dealership-owned tyres at reseller locations, filterable by reseller, location, brand, size, SKU and availability; with value. Excludes sold stock; in-transit stock is shown separately and never double-counted.
2. **Backorders awaiting replenishment** — by reseller, SKU, outstanding, reason, age, priority, expected date, status; distinguishes allocated from awaiting supply.
3. **Reseller transaction history** — chronological ledger with opening balance, receipts, sales, invoice references, replenishments, transfer in/out, adjustments, outstanding obligations and running SKU balances.

Additional: warehouse availability, demand by SKU, sold-but-uninvoiced, transfers, stocktake discrepancies, dashboard.

### 4.12 Identity, access, audit [BC §4, §13; MI §5]
- Roles (pilot): Relationship Manager, Warehouse Manager, Sales Representative, Reseller. The business case's administrator and finance duties are covered by the Relationship Manager (user administration and invoicing); see `docs/PILOT_USERS.md`.
- Permissions are enforced in the backend. Reseller users see only their own reseller's data.
- Sensitive actions (adjustments, transfer approval, backorder cancellation, invoice void) need specific permissions.
- An audit log records significant administrative, inventory and financial actions with user, timestamp and reason.

## 5. Non-functional requirements [MI §3, §6]
- Transaction-based, append-only inventory ledger; balances reconcilable from history.
- Atomic operations; concurrency-safe (row locks plus DB check constraints); no negative available stock.
- Modular monolith; PostgreSQL; low-cost deployability; no paid infrastructure at MVP.
- Branding configurable in one place.
- Responsive UI for desktop, tablet and mobile.

## 6. Out of scope for the MVP (deferred, clearly marked in the UI)
- Reseller self-service write actions (sales reporting, delivery acknowledgement) — BC Phase 2.
- Notifications [BC §12].
- Credit notes and returned-goods processing (reversals of *uninvoiced* sales are supported).
- Live accounting-platform integration (the export boundary only).
- Forecasting, transfer recommendations, ageing analytics [BC Phase 3].
- Batch / DOT tracking.

## 7. Decisions requiring dealership validation [BC §16]
These are tracked in `DECISION_LOG.md` with the assumption currently implemented:
ownership and transfer rights per agreement; how sales are reported; invoice timing, terms, pricing and tax; targets and whether every sale triggers replacement; source-reseller consent rules; allocation priority when supply is short; systems to integrate with; returns, damage, discrepancy and account-closure procedures.
