# TyreGrow — Data Model

PostgreSQL. Integer surrogate keys. Business documents also carry a human-readable `number` (for example `SAL-000001`). Timestamps are `timestamptz`. Money is `numeric(12,2)` and tax rates are `numeric(6,4)`. Enums are stored as constrained strings.

Legend: **PK** primary key, **FK** foreign key, **UQ** unique, **CK** check constraint.

## Identity and audit

### users
`id` PK · `email` UQ · `full_name` · `phone` (optional, shown to dealers as a contact; 0016) · `password_hash` (bcrypt) · `role` (ADMINISTRATOR | RELATIONSHIP_MANAGER | WAREHOUSE_MANAGER | SALES_REP | RESELLER | FINANCE_MANAGER) · `must_change_password` · `reseller_id` FK → resellers · `is_active` · timestamps.
CK: `role = 'RESELLER'` ⇔ `reseller_id IS NOT NULL`.

### audit_events (append-only)
`id` · `occurred_at` · `actor_user_id` FK · `action` (for example `transfer.approve`) · `entity_type` · `entity_id` · `reseller_id` FK (for scoping and filtering) · `summary` · `details` jsonb.

### number_sequences
`prefix` PK · `next_value`. Updated with `UPDATE … RETURNING`, which takes a row lock.

## Catalogue

### products
`id` · `sku` UQ · `brand` · `pattern` · `width` · `aspect_ratio` · `rim_diameter` numeric(4,1) · `construction` (default R) · `load_index` · `speed_rating` · `description` · `barcode` UQ nullable · `cost_price` · `list_price` · `is_active`.
CK positive dimensions and non-negative prices. Index on (width, aspect_ratio, rim_diameter) for size search. Size equality never implies interchangeability.
**0022 (white-label 1.4):** `attributes` jsonb NOT NULL default `{}` (GIN index) holds Industry Pack attributes for
non-tyre packs; the five tyre columns are nullable (the tyres pack still requires them); CK `tyre_size_complete`
keeps width / aspect / rim all set or all null.

### tax_rates
`id` · `code` UQ · `name` · `rate` (fraction, 0 ≤ rate < 1) · `is_default` (partial unique index: at most one default) · `is_active`.

## Customers

### resellers
`id` · `account_ref` UQ · `business_name` · `trading_name` · `contact_name` · `email` · `phone` · `billing_address` · `tax_number` · `sales_rep_user_id` FK → users · `payment_terms_days` · `tax_rate_id` FK (override) · `status` (ACTIVE | ON_HOLD | CLOSED) · `notes`.

### consignment_agreements (1:1 reseller)
`id` · `reseller_id` UQ FK · `reference` · `start_date` · `end_date` · `transfer_consent` (PRE_AUTHORISED | PER_TRANSFER | NOT_ALLOWED) · `auto_replenish_default` · `notes`.

### locations
`id` · `code` UQ · `name` · `type` (WAREHOUSE | CONSIGNMENT | TRANSIT | SUPPLIER | SOLD | ADJUSTMENT | OPENING | SCRAP) · `reseller_id` FK · `is_default_warehouse` · address fields · `is_active`.
CK: `type = 'CONSIGNMENT'` ⇔ `reseller_id IS NOT NULL`. System locations (`SYS-*`) are created by migration 0001.

### customer_prices
`id` · `reseller_id` FK · `product_id` FK · `unit_price` · `valid_from` · `valid_to` · `created_by_user_id`. UQ (reseller, product, valid_from).

## Consignment

### consignment_allocations
`id` · `location_id` FK (consignment) · `product_id` FK · `target_qty` · `min_qty` · `max_qty` · `auto_replenish` · `is_active`. UQ (location, product). CK `max ≥ target`.

### allocation_changes (append-only)
`id` · `allocation_id` FK · `old_target_qty` · `new_target_qty` · `old_auto_replenish` · `new_auto_replenish` · `reason` · `changed_by_user_id` · `changed_at`.

## Inventory core

### inventory_transactions (append-only header)
`id` · `number` UQ (`TXN-…`) · `txn_type` · `occurred_at` · `actor_user_id` · `approved_by_user_id` · `reference_type` / `reference_id` / `reference_number` (the business document) · `reason` · `notes` · `reverses_transaction_id` FK self.

### inventory_entries (append-only lines)
`id` · `transaction_id` FK · `product_id` · `location_id` · `bucket` (ON_HAND | RESERVED | BLOCKED) · `quantity` (signed, CK ≠ 0) · `reservation_id` FK.
Invariant: for each transaction, Σ ON_HAND quantity = 0.

### stock_balances (projection; physical locations only)
PK (`location_id`, `product_id`) · `on_hand` · `reserved` · `blocked` · `updated_at`.
CK `on_hand ≥ 0`, `reserved ≥ 0`, `blocked ≥ 0`, `reserved + blocked ≤ on_hand`.
Invariant: equals Σ entries per (location, product, bucket).

### stock_reservations
`id` · `location_id` · `product_id` · `quantity` · `consumed_qty` · `released_qty` · `status` (ACTIVE | CONSUMED | RELEASED | CLOSED) · `purpose` (REPLENISHMENT | TRANSFER) · `reference_type` / `reference_id` · `created_by_user_id` · `created_at`.
CK `consumed + released ≤ quantity`.

## Workflows and invoicing (migration 0002)

### purchase_orders / purchase_order_lines
PO: `id` · `number` (`PO-…`) · `supplier_name` · `supplier_reference` · `warehouse_location_id` · `expected_date` · `status` (OPEN | PARTIALLY_RECEIVED | RECEIVED | CANCELLED) · `notes` · `created_by_user_id`.
Line: `id` · `purchase_order_id` · `product_id` · `qty_ordered` · `qty_received` · `unit_cost`. CK `0 ≤ received ≤ ordered`.
Incoming quantity = ordered − received on open POs. It is never stock.

### goods_receipts / goods_receipt_lines
Receipt: `id` · `number` (`GRN-…`) · `purchase_order_id` (nullable: ad hoc receipt) · `warehouse_location_id` · `supplier_reference` · `received_at` · `received_by_user_id` · `inventory_transaction_id` · `notes`.
Line: `id` · `goods_receipt_id` · `purchase_order_line_id` · `product_id` · `qty_received` · `qty_damaged` (blocked on receipt).

### consignment_sales / consignment_sale_lines
Sale: `id` · `number` (`SAL-…`) · `reseller_id` · `location_id` · `sale_date` · `source` (RESELLER_REPORT | STOCKTAKE | REP_VISIT | OTHER) · `source_reference` · `stocktake_id` · `recorded_by_user_id` · `recorded_at` · `inventory_transaction_id` · `notes`.
Line: `id` · `sale_id` · `product_id` · `quantity` · `reversed_qty` · `unit_price` · `price_source` · `tax_rate_id` · `tax_code` · `tax_rate` (snapshots) · `invoice_status` (UNINVOICED | DRAFTED | INVOICED | NOT_CHARGEABLE).
CK `0 ≤ reversed_qty ≤ quantity`. Chargeable quantity = quantity − reversed_qty.

### replenishment_requests (demand; "backorder" = awaiting-supply part)
`id` · `number` (`REP-…`) · `reseller_id` · `location_id` · `product_id` · `reason` (SALE | TRANSFER | TARGET_SHORTFALL | MANUAL) · `origin_type` / `origin_id` / `origin_number` · `sale_line_id` FK · `transfer_id` FK · `qty_required` · `qty_allocated` · `qty_in_transit` · `qty_transfer_covered` (covered by a linked approved/in-transit transfer) · `qty_delivered` · `qty_cancelled` · `priority` (URGENT | HIGH | NORMAL | LOW) · `expected_date` · `purchase_order_line_id` FK (supply reference) · `status` · `notes` · `created_by_user_id` · `created_at` · `closed_at`.
CK all quantities ≥ 0 and `allocated + in_transit + transfer_covered + delivered + cancelled ≤ required`.

### replenishment_events (append-only history per request)
`id` · `request_id` · `event_type` (CREATED | ALLOCATED | ALLOCATION_RELEASED | DISPATCHED | DELIVERED | SHORT_DELIVERED | RETURNED | LOST | CANCELLED | PRIORITY_CHANGED | EXPECTED_DATE_CHANGED | SUPPLY_LINKED | TRANSFER_COVERED | TRANSFER_COVER_RELEASED) · `quantity` · `reference_type` / `reference_id` / `reference_number` · `reason` · `actor_user_id` · `occurred_at`.

### replenishment_allocations
`id` · `request_id` · `reservation_id` · `warehouse_location_id` · `quantity` · `dispatched_qty` · `released_qty` · `status` (ACTIVE | DISPATCHED | RELEASED | CLOSED) · `created_by_user_id` · `created_at`.

### deliveries / delivery_lines
Delivery: `id` · `number` (`DEL-…`) · `from_location_id` · `to_location_id` · `reseller_id` · `status` (IN_TRANSIT | RECEIVED | RECEIVED_WITH_DISCREPANCY | CLOSED) · `dispatched_at/by` · `received_at/by` · `carrier_reference` · `dispatch_transaction_id` · `notes`.
Line: `id` · `delivery_id` · `request_id` · `allocation_id` · `product_id` · `qty_dispatched` · `qty_received` · `qty_returned` · `qty_lost` · `qty_late_received`.
Open in-transit quantity per line = dispatched − received − returned − lost − late_received.

### transfers
`id` · `number` (`TRF-…`) · `product_id` · `quantity` · `destination_location_id` / `destination_reseller_id` · `source_location_id` / `source_reseller_id` · `reason` · `urgency` · `status` (REQUESTED | APPROVED | IN_TRANSIT | RECEIVED_WITH_DISCREPANCY | COMPLETED | CANCELLED | REJECTED) · `requested_by/at` · `approved_by/at` · `approval_notes` · `source_consent_reference` · `reservation_id` · `collected_by/at` · `qty_collected` · `received_by/at` · `qty_received` · `qty_returned` · `qty_lost` · `destination_request_id` FK (destination demand it fulfils) · `source_request_id` FK (source replacement obligation) · `cancelled_by/at` · `cancel_reason` · `notes`.

### stocktakes / stocktake_lines
Stocktake: `id` · `number` (`STK-…`) · `location_id` · `reseller_id` · `count_date` · `counted_by_user_id` · `status` (DRAFT | SUBMITTED | APPROVED | CANCELLED) · `submitted_at` · `approved_by/at` · `sale_id` · `notes`.
Line: `id` · `stocktake_id` · `product_id` · `expected_qty` / `expected_blocked_qty` (snapshots at submission) · `counted_qty` · `counted_damaged_qty` · `qty_sold` · `qty_missing` · `notes`. Variance = counted − expected.

## Invoicing (migration 0002)

### invoices
`id` · `number` (`INV-…`) · `reseller_id` · `status` (DRAFT | ISSUED | VOID) · `invoice_date` · `due_date` · `currency` · `subtotal` · `tax_total` · `total` · billing snapshot (`bill_to_name`, `bill_to_account_ref`, `bill_to_address`, `bill_to_tax_number`) · `external_reference` (accounting system id) · `exported_at` · `created_by/at` · `issued_by/at` · `voided_by/at` · `void_reason` · `notes`.

### invoice_lines
`id` · `invoice_id` · `sale_line_id` FK · `sale_number` · `sale_date` · `location_code` · `sku` · `description` · `quantity` · `unit_price` · `tax_code` · `tax_rate` · `line_net` · `line_tax` · `line_total` · `is_active`.
**Partial unique index on `sale_line_id` WHERE `is_active`**: a sale line can be on only one non-void invoice (duplicate-invoice prevention at database level).

## Release 1.11.0 (migrations 0011–0016, all additive)

| Migration | Table | Added |
|---|---|---|
| 0011 | **consignment_agreement_files** (new) | `id` · `reseller_id` FK · `filename` · `content_type` (PDF, JPEG, PNG, WEBP) · `size_bytes` (≤ 5 MB) · `data` bytea · `uploaded_by_user_id` FK · `uploaded_at` · `is_active`. Account references (AKT-AUC-001) and shop codes (…-01) use `number_sequences` and the existing columns. |
| 0012 | stock_requests | `approval_method` · `approval_contact` · `approval_comments` · `escalated_to_user_id` / `escalated_by_user_id` FK users · `escalated_at` · `escalation_note` |
| 0013 | replenishment_requests | `approval_method` · `approval_contact` · `approval_comments` · `approved_by_user_id` FK · `approved_at` · `escalated_to_user_id` / `escalated_by_user_id` FK · `escalated_at` · `escalation_note` · `ready_at` · `ready_by_user_id` FK |
| 0014 | transfers | `shipping_method` (COURIER / SALES_REP; null = not arranged) · `carrier_reference` · `tracking_number` · `carried_by_user_id` FK · `shipping_arranged_at` · `shipping_arranged_by_user_id` FK · `collected_from_name` · `note_emailed_at` · `note_email_to` · `note_email_error` |
| 0015 | invoices | `xero_recorded_by_user_id` FK · `xero_recorded_at`. The Xero invoice number is the existing `external_reference`. |
| 0016 | stocktakes, users | stocktakes: `recheck_requested_at` · `recheck_requested_by_user_id` FK · `recheck_note` · `disputed_at` · `disputed_by_user_id` FK · `dispute_note` · `recount_of_id` FK self. users: `phone`. New stocktake statuses RECHECK_REQUESTED, DISPUTED, SUPERSEDED fit the existing `status` string. |

Every new column is nullable; existing rows keep today's behaviour. Each migration has a working downgrade.

## Key relationships

```
Reseller 1─* Location(CONSIGNMENT) 1─* ConsignmentAllocation *─1 Product
Location 1─* StockBalance *─1 Product
InventoryTransaction 1─* InventoryEntry ─> Location, Product, [StockReservation]
ConsignmentSale 1─* SaleLine ─1 ReplenishmentRequest(reason=SALE)      SaleLine 1─0..1 active InvoiceLine
Transfer ─1 ReplenishmentRequest(reason=TRANSFER, source reseller)     Transfer ─0..1 ReplenishmentRequest(destination demand)
ReplenishmentRequest 1─* ReplenishmentAllocation ─1 StockReservation
ReplenishmentRequest 1─* DeliveryLine *─1 Delivery
PurchaseOrder 1─* POLine 1─* GoodsReceiptLine;  POLine 0..1─* ReplenishmentRequest (expected supply)
Stocktake 1─* StocktakeLine; Stocktake ─0..1 ConsignmentSale; Stocktake ─0..1 Stocktake (recount_of)
Reseller 1─* ConsignmentAgreementFile
```

### pilot_feedback
`id` PK · `user_id` FK users · `role` (as submitted) · `page` · `feedback_type` (ISSUE | IMPROVEMENT | QUESTION | OTHER) · `description` · `created_at` / `updated_at`. Written by `POST /api/feedback`; reviewed by roles with `audit.read`.
