# TyreGrow — Inventory Rules

These rules are the contract for the inventory core (`backend/app/modules/inventory`). Business workflows (sales, replenishment, transfers, stocktakes, purchasing) may change stock **only** through the inventory service.

## 1. Locations

Every unit of stock is in exactly one location at any time.

| Type | Physical? | Balance tracked? | Purpose |
|---|---|---|---|
| `WAREHOUSE` | yes | yes | Dealership warehouse(s). One is flagged as the default. |
| `CONSIGNMENT` | yes | yes | A reseller's premises. Always linked to a reseller. |
| `TRANSIT` | yes (goods on the road) | yes | A single system location holding dispatched-but-not-received stock. |
| `SUPPLIER` | virtual | no | Source of supplier receipts. |
| `SOLD` | virtual | no | Destination of confirmed reseller sales to end customers. |
| `ADJUSTMENT` | virtual | no | Counterpart for approved gains and losses (stocktake, correction, lost in transit). |
| `OPENING` | virtual | no | Counterpart for opening balances. |
| `SCRAP` | virtual | no | Destination for written-off damaged stock. |

Virtual locations are system data created by migration, identified by a fixed `code`. Because every physical movement goes *from* one location *to* another, the ledger is double-entry: **the sum of `ON_HAND` entries in every transaction is zero**. Stock is conserved, and the same tyre can never be counted in two places.

## 2. Buckets

For each physical location and product, `stock_balances` holds:

- `on_hand`: physical quantity present, including reserved and blocked units.
- `reserved`: part of on-hand committed to a movement (replenishment dispatch or transfer collection).
- `blocked`: part of on-hand that is damaged, quarantined or otherwise unavailable.
- **available = on_hand − reserved − blocked** [BC §9] (computed, never stored).

Database check constraints enforce `on_hand ≥ 0`, `reserved ≥ 0`, `blocked ≥ 0` and `reserved + blocked ≤ on_hand`, so **available can never go negative**, even if application logic is wrong. The MVP has no negative-stock exception workflow.

Quantities that are **not** physical stock, and are never stored in `stock_balances`:
- **In transit**: physically in the `TRANSIT` location, attributed to a delivery or transfer document.
- **Sold but uninvoiced**: sale lines with `invoice_status != INVOICED`.
- **Outstanding replenishment demand**: replenishment requests.
- **Incoming**: open purchase order line quantity (`ordered − received`).

## 3. The ledger

- `inventory_transactions`: header. Number, type, timestamp, actor, business reference (type, id, number), reason, notes, approving user, and `reverses_transaction_id` for compensating entries.
- `inventory_entries`: signed quantity deltas by (product, location, bucket), optionally linked to a reservation.

Entries are **append-only**. The application exposes no update or delete for entries or transactions. Corrections are new compensating transactions (for example, a sale reversal moves stock `SOLD → location` and references the original).

Each balance change and its ledger entries are written in the **same database transaction**, so the two cannot diverge. `GET /api/inventory/reconciliation` rebuilds every balance from entries and reports any difference (acceptance test 8).

### Transaction types
| Type | Entries |
|---|---|
| `OPENING_BALANCE` | OPENING → location (on_hand) |
| `SUPPLIER_RECEIPT` | SUPPLIER → warehouse (on_hand); damaged units are also blocked |
| `ADJUSTMENT` | ADJUSTMENT ↔ location (on_hand), approved, with reason |
| `BLOCK` / `UNBLOCK` | ±blocked at location |
| `WRITE_OFF` | location → SCRAP (on_hand), −blocked |
| `RESERVATION` / `RESERVATION_RELEASE` | ±reserved at location |
| `REPLENISHMENT_DISPATCH` | warehouse → TRANSIT (on_hand), −reserved at warehouse |
| `REPLENISHMENT_RECEIPT` | TRANSIT → consignment location |
| `TRANSFER_COLLECTION` | source → TRANSIT, −reserved at source |
| `TRANSFER_RECEIPT` | TRANSIT → destination |
| `TRANSIT_RESOLUTION` | TRANSIT → origin (return), → ADJUSTMENT (lost), or → destination (late) |
| `CONSIGNMENT_SALE` | consignment location → SOLD |
| `SALE_REVERSAL` | SOLD → consignment location (compensating) |
| `STOCKTAKE_ADJUSTMENT` | ADJUSTMENT ↔ location; ±blocked for damaged |

## 4. Concurrency

- Every stock-changing operation runs in one DB transaction.
- The affected `stock_balances` rows are created if missing (`INSERT … ON CONFLICT DO NOTHING`), then locked with `SELECT … FOR UPDATE` **in a deterministic order** (location id, product id) to minimise deadlocks.
- Availability is checked *after* acquiring the lock. A concurrent second request waits, then sees the reduced availability and is rejected with HTTP 409.
- Workflow documents (replenishment requests, transfers, deliveries, stocktakes, allocations) are also locked with `FOR UPDATE` before a state transition, which makes double-submits harmless.
- Check constraints are the final backstop (acceptance test 5).
- A detected deadlock or serialisation failure is returned as HTTP 409 "please retry" and nothing is committed.

## 5. Replenishment demand rules

Quantities on a request (all ≥ 0, checked by constraint):

```
outstanding     = required − delivered − cancelled
awaiting_supply = outstanding − allocated − in_transit − transfer_covered      (the "backorder" quantity)
allocated + in_transit + transfer_covered + delivered + cancelled ≤ required
```

Derived status (priority order): `CANCELLED` (all cancelled) → `FULFILLED` (outstanding = 0) → `IN_TRANSIT` (in_transit > 0) → `ALLOCATED` (allocated > 0 or transfer_covered > 0) → `PARTIALLY_FULFILLED` (delivered > 0) → `OPEN`.

**Backorder** = a request with `awaiting_supply > 0`. The Backorders view and report filter on this, and also show the allocated and in-transit quantities of each request.

### Shortfall and duplicate prevention [BC §9, MI §2 S1]
For a consignment location L and product P with an active allocation (target T):

```
covered   = on_hand(L,P) + Σ outstanding(open requests for L,P) + Σ open inbound transfers to L for P
shortfall = max(0, T − covered)
```

- **Sale-triggered** request quantity = `min(sold quantity, shortfall)`. Nothing is created if the allocation has `auto_replenish = false`, or if no allocation exists. Replenishment therefore never exceeds the target.
- **Transfer-triggered** request quantity = quantity collected from the source. This restores the source's allocation and is created regardless of target, because it is an obligation to that reseller [BC §8].
- **Target-shortfall** requests (`POST /api/replenishment/generate-shortfalls`) create `shortfall` for each allocation.
- **Manual** requests are allowed above the shortfall only with the `replenishment.override` permission, and need a reason.
- The allocation row is locked `FOR UPDATE` while the shortfall is computed, so concurrent sales cannot both create demand for the same gap.

### Allocation and fulfilment
- **Allocate**: lock the request and the warehouse balance; reserve `min(requested, awaiting_supply, available)`; record a `replenishment_allocations` row linked to the reservation; `allocated += q`.
- New requests are allocated immediately from the default warehouse when `AUTO_ALLOCATE_ON_CREATE=true` (default) **and the reseller is ACTIVE**. Anything that cannot be allocated remains as a backorder.
- **Goods receipts never allocate automatically.** `GET /api/replenishment/allocation-proposal` proposes allocations using the configured policy (`PRIORITY_THEN_OLDEST`), and a user confirms them.
- **Dispatch**: consumes the reservation; warehouse → TRANSIT; `allocated −= q`, `in_transit += q`. The delivery document records each line.
- **Receipt**: TRANSIT → reseller; `in_transit −= dispatched`, `delivered += received`. A short quantity stays in transit, attributed to the delivery line, until resolved:
  - *return to warehouse* (TRANSIT → warehouse; the request's quantity returns to awaiting supply);
  - *lost* (TRANSIT → ADJUSTMENT; returns to awaiting supply);
  - *late delivery* (TRANSIT → reseller; `delivered += q`).
- **Cancellation** (permission `replenishment.cancel`, reason required) applies only to the awaiting-supply quantity. Active allocations must be released first.
- **Priority change** (permission `replenishment.manage`) requires a reason and is audited.
- **No invoice is ever produced by replenishment.**

## 6. Transfer rules

| Step | Stock effect | Demand effect |
|---|---|---|
| Request | none | destination need recorded (optionally linked to an open destination request) |
| Approve (source chosen) | reserve qty at source (fails if source available < qty) | linked destination request: `transfer_covered += qty` |
| Cancel before collection | release reservation | linked destination request: `transfer_covered −= qty`; no obligation was ever created |
| Collect | source → TRANSIT (consumes reservation) | create `TRANSFER` request for the source, linked to the transfer |
| Receive (qty r ≤ collected) | TRANSIT → destination (r) | if linked, destination request `transfer_covered −= r`, `delivered += r` |
| Resolve discrepancy: return | TRANSIT → source | source request: cancel the returned qty (awaiting supply only) |
| Resolve discrepancy: lost | TRANSIT → ADJUSTMENT | source obligation remains |
| Resolve discrepancy: late delivery | TRANSIT → destination | as receive |

- Only `available` stock (not sold, reserved or blocked) at an **active** reseller's consignment location can be a source. The source must differ from the destination.
- Source consent: when the agreement's `transfer_consent` is `PER_TRANSFER`, the approver must record the consent reference. `NOT_ALLOWED` blocks the source.
- A transfer never creates a sale or an invoice line.
- Linking a transfer to the destination's open backorder prevents over-supply: the covered quantity is not also allocated from the warehouse. Unlinked inbound transfers count as coverage when computing target shortfalls.
- Reseller users see only their own side of a transfer; the counterparty is shown as "Another reseller".

## 7. Sales and stocktake rules
- A sale requires `available ≥ qty` at the location (reserved or blocked stock cannot be sold).
- Price is snapshotted when the sale is recorded: an effective customer-specific price first, otherwise the product list price. A manual price is allowed with a reason. Since 1.11.0 prices are set in Xero (P-030): a sale with no agreed price is recorded as "not priced" (0.00) and no screen shows prices.
- Reversal (permission `sales.reverse`) applies only to uninvoiced quantity. It posts SOLD → location, and cancels up to the reversed quantity from the linked request's awaiting-supply portion.
- Stock check shortage (`expected − counted`), since 1.11.0 (P-042, D3):
  - On submission the shortage is **held** (blocked) so it cannot be sold or moved, and the dealer has `STOCKTAKE_FIND_DAYS` (5) calendar days to find the tyres.
  - Nothing is written off as missing: `confirm` with `qty_missing > 0` is refused ("In consignment, tyres that aren't found are re-checked or invoiced."). Every tyre not found is either re-checked or invoiced as sold.
  - **Re-check:** the dealer asks; staff start a **re-count**, which releases the hold, marks the check SUPERSEDED and opens a new draft for the same shop with the shortage SKUs (`recount_of_id`). Re-check requested and disputed checks pause the clock.
  - **Invoiced as sold:** by the dealer, by staff on the dealer's behalf (with a reason), or automatically when the days run out (`auto_invoice_due`, a system actor). The hold is released and the sold quantity becomes a confirmed sale (source STOCKTAKE) with an invoice record and a replacement, through the same ledger postings as any sale.
  - A surplus is posted as an approved adjustment gain. Counted-damaged units are blocked.
- **Legacy path:** counts submitted before P-018 (status SUBMITTED) keep `sold + missing = shortage` classification and staff approval, including "missing" (an approved loss). A legacy stocktake cannot be approved if the location's on-hand has changed since the count was submitted (recount required).

## 8. Initial stock corrections
- A dealer's initial stock that was entered wrongly is corrected by the **Relationship Manager or Administrator** only (`initial_stock.correct`), with a reason (at least 5 characters). The Warehouse Manager cannot.
- The original opening balance is never changed. A correction is a new transaction, `INITIAL_STOCK_CORRECTION`, with `reverses_transaction_id` = the entry it corrects. It moves only the difference: tyres taken out go back to `SYS-OPENING` (they were never there); tyres added come from it. Totals still reconcile.
- Only **available** stock at the shop can be taken out: tyres sold, reserved or blocked cannot be corrected away.
- Allowed until the **first stock check** at that shop (any count past draft) and for `INITIAL_STOCK_CORRECTION_DAYS` (30) after the entry. After that, differences go through a stock check (section 7).
- A correction is never invoiced and raises no replacement.
- Every correction is in the change history (`inventory.initial_stock_correct`: who, when, before → after per tyre, the reason), notifies Administrators and Finance Managers, shows on the dealer's Dealer history tab beside the original entry, in "Where did this tyre come from?", in the dealer transaction history ("Initial stock corrected") and in Reports → Stock corrections.

## 9. Transfers via the warehouse and stock-request shortfalls (UAT round 2)
- A transfer's route is chosen when its pick-up is arranged: `DIRECT` (default; existing transfers) or `VIA_WAREHOUSE`.
- Via the warehouse, collection posts SOURCE → TRANSIT as for any transfer. The warehouse then records that it received and checked the tyres (`warehouse_received_at/by`, notes, optional photos) **without a ledger posting**: the stock stays in TRANSIT until it is delivered (TRANSIT → destination). Delivery is refused until the warehouse check is recorded.
- Approving a stock request line with `remainder = TRANSFER` backorders the rest (as `BACKORDER`) and raises a transfer request linked to that backorder (`destination_request_id`). Section 6 applies to the transfer unchanged; when it is delivered, the backorder and the stock request follow.
