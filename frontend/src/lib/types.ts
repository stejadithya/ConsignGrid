/** Types mirroring the backend API responses (see the schemas.py file in each backend module). */

export type RoleCode = "ADMINISTRATOR" | "RELATIONSHIP_MANAGER" | "WAREHOUSE_MANAGER" | "SALES_REP" | "RESELLER" | "FINANCE_MANAGER";

export interface Me {
  id: number;
  email: string;
  full_name: string;
  role: RoleCode;
  role_label: string;
  reseller_id: number | null;
  is_active: boolean;
  must_change_password: boolean;
  permissions: string[];
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: string;
  reseller_id: number | null;
  is_active: boolean;
  phone?: string | null;   // shown to dealers as a contact (1.11)
  locked_until?: string | null;   // set while locked after too many wrong passwords
}

export interface Product {
  id: number;
  sku: string;
  brand: string;
  pattern: string;
  width: number;
  aspect_ratio: number;
  rim_diameter: string;
  construction: string;
  load_index: string;
  speed_rating: string;
  size_display: string;
  display_name: string;
  description: string | null;
  barcode: string | null;
  list_price: string | null;
  rrp: string | null;
  cost_price: string | null;
  is_active: boolean;
}

export interface TaxRate {
  id: number;
  code: string;
  name: string;
  rate: string;
  is_default: boolean;
  is_active: boolean;
}

export interface Location {
  id: number;
  code: string;
  name: string;
  type: string;
  reseller_id: number | null;
  reseller_name?: string | null;   // the dealer's business name (consignment shops)
  is_default_warehouse: boolean;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  region: string | null;
  postcode: string | null;
  country: string | null;
  contact_phone: string | null;
  is_active: boolean;
}

export interface Agreement {
  id: number;
  reference: string;
  start_date: string | null;
  end_date: string | null;
  transfer_consent: string;
  auto_replenish_default: boolean;
  notes: string | null;
}

export interface ResellerSummary {
  id: number;
  account_ref: string;
  business_name: string;
  trading_name: string | null;
  status: string;
  sales_rep_user_id: number | null;
  sales_rep_name: string | null;
  location_count: number;
}

export interface Reseller extends ResellerSummary {
  /** true = joined already holding TyreGrow stock; false = new dealer (stock through requests); null = added before 1.12 */
  joined_with_stock?: boolean | null;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  billing_address: string | null;
  tax_number: string | null;
  payment_terms_days: number | null;
  tax_rate_id: number | null;
  notes: string | null;
  agreement: Agreement | null;
  locations: Location[];
  /** Only in the response that created the dealer together with its login (shown once). */
  login?: { email: string; temporary_password: string } | null;
}

export interface CustomerPrice {
  id: number;
  reseller_id: number;
  product_id: number;
  sku: string | null;
  unit_price: string;
  valid_from: string;
  valid_to: string | null;
}

export interface Balance {
  location_id: number;
  location_code: string;
  location_name: string;
  location_type: string;
  reseller_id: number | null;
  product_id: number;
  sku: string;
  product_name: string;
  on_hand: number;
  reserved: number;
  blocked: number;
  available: number;
}

export interface Entry {
  id: number;
  product_id: number;
  location_id: number;
  bucket: string;
  quantity: number;
  reservation_id: number | null;
}

export interface InventoryTransaction {
  id: number;
  number: string;
  txn_type: string;
  occurred_at: string;
  actor_user_id: number | null;
  approved_by_user_id: number | null;
  reference_type: string | null;
  reference_id: number | null;
  reference_number: string | null;
  reason: string | null;
  notes: string | null;
  entries: Entry[];
}

export interface Reconciliation {
  balanced: boolean;
  checked_at: string;
  differences: { location_id: number; product_id: number; bucket: string; ledger_qty: number; balance_qty: number }[];
  unbalanced_transaction_ids: number[];
}

export interface AllocationPosition {
  allocation_id: number | null;
  location_id: number;
  location_code: string;
  reseller_id: number;
  product_id: number;
  sku: string;
  product_name: string;
  target_qty: number;
  auto_replenish: boolean;
  on_hand: number;
  reserved: number;
  blocked: number;
  available: number;
  open_replenishment: number;
  replenishment_in_transit: number;
  transfers_inbound: number;
  remaining_unmet: number;
}

export interface LinkedRequest {
  id: number;
  number: string;
  qty_required: number;
  status: string;
  qty_in_transit?: number;
  qty_delivered?: number;
  deliveries?: { id: number; number: string; status: string; dispatched_at: string; received_at: string | null }[];
}

export interface SaleLine {
  id: number;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  quantity: number;
  reversed_qty: number;
  chargeable_qty: number;
  unit_price: string;
  price_source: string;
  tax_code: string;
  tax_rate: string;
  line_net: string;
  invoice_status: string;
  invoice_number: string | null;       // RM/FM/Admin, and the dealer for their own sales (D12)
  replenishment: LinkedRequest[];
  invoice_state?: "NOT_INVOICED" | "INVOICE_DRAFTED" | "INVOICED";
  invoiced?: boolean;
  xero_reference?: string | null;      // RM/FM/Admin only
  invoiced_at?: string | null;
}

export interface Sale {
  id: number;
  number: string;
  reseller_id: number;
  reseller_name: string | null;
  location_id: number;
  location_code: string | null;
  sale_date: string;
  source: string;
  source_reference: string | null;
  stocktake_id: number | null;
  recorded_by: string | null;
  recorded_at: string;
  notes: string | null;
  total_qty: number;
  total_net: string;
  lines: SaleLine[];
  customer_name?: string | null;
  customer_phone?: string | null;
}

export interface ReplenishmentRequest {
  id: number;
  number: string;
  reseller_id: number;
  reseller_name: string | null;
  location_id: number;
  location_code: string | null;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  reason: string;
  origin_type: string | null;
  origin_id: number | null;
  origin_number: string | null;
  sale_line_id: number | null;
  transfer_id: number | null;
  qty_required: number;
  qty_allocated: number;
  qty_in_transit: number;
  qty_transfer_covered: number;
  qty_delivered: number;
  qty_cancelled: number;
  qty_outstanding: number;
  qty_awaiting_supply: number;
  priority: string;
  expected_date: string | null;
  purchase_order_line_id: number | null;
  status: string;
  notes: string | null;
  created_at: string;
  closed_at: string | null;
  age_days: number;
  raised_by?: string | null;
  raised_by_role?: RoleCode | null;
  first_supply?: boolean;
  // Fulfilment on the request (1.11). Approval and escalation details are staff only.
  awaiting_approval?: boolean;
  auto_approved?: boolean;
  approved_by?: string | null;
  approved_at?: string | null;
  approval_method?: string | null;
  approval_contact?: string | null;
  approval_comments?: string | null;
  escalated_to_user_id?: number | null;
  escalated_to?: string | null;
  escalated_by?: string | null;
  escalated_at?: string | null;
  escalation_note?: string | null;
  ready?: boolean;
  ready_at?: string | null;
  ready_by?: string | null;
}

/** Another dealer's request in a transfer chain (staff only). */
export interface LinkedRequestSummary { id: number; number: string; reseller_name: string; status: string; qty_awaiting_supply: number }

/** A transfer covering a request, and the replacement it raised for the dealer who gave the tyres. */
export interface CoveringTransfer {
  id: number; number: string; status: string; quantity: number; source_reseller_name: string | null;
  replacement: LinkedRequestSummary | null;
}

export interface RequestDetail extends ReplenishmentRequest {
  covered_by_transfers?: CoveringTransfer[];
  fills_request?: LinkedRequestSummary | null;
  events: {
    id: number;
    event_type: string;
    quantity: number | null;
    reference_type: string | null;
    reference_id: number | null;
    reference_number: string | null;
    reason: string | null;
    actor_name: string | null;
    occurred_at: string;
  }[];
  allocations: {
    id: number;
    warehouse_location_id: number;
    quantity: number;
    dispatched_qty: number;
    released_qty: number;
    open_qty: number;
    status: string;
    created_at: string;
  }[];
  delivery_lines: {
    delivery_id: number;
    delivery_number: string;
    delivery_status: string;
    qty_dispatched: number;
    qty_received: number;
    qty_open: number;
  }[];
  deliveries?: Delivery[];
}

export interface DeliveryLine {
  id: number;
  request_id: number;
  request_number: string | null;
  product_id: number;
  sku: string | null;
  qty_dispatched: number;
  qty_received: number;
  qty_returned: number;
  qty_lost: number;
  qty_late_received: number;
  qty_open: number;
}

export interface Delivery {
  id: number;
  number: string;
  from_location_id: number;
  from_location_code: string | null;
  to_location_id: number;
  to_location_code: string | null;
  reseller_id: number;
  reseller_name: string | null;
  status: string;
  carrier_reference: string | null;
  dispatched_at: string;
  dispatched_by: string | null;
  received_at: string | null;
  received_by: string | null;
  notes: string | null;
  lines: DeliveryLine[];
  tracking_number?: string | null;
  shipping_address?: string | null;
  stock_request_id?: number | null;
  stock_request_number?: string | null;
  delivered_on?: string | null;
  delivery_reference?: string | null;
  receipt_notes?: string | null;
  shipping_method?: "COURIER" | "SALES_REP";
  carried_by_user_id?: number | null;
  carried_by?: string | null;
  note_emailed_at?: string | null;
  note_email_to?: string | null;
  note_email_error?: string | null;
  received_by_name?: string | null;   // who at the dealer took the stock (recorded by a Sales Rep)
  photos?: number[];                   // drop-off photo ids
  photos_retired?: number;             // archived or deleted under the photo archiving setting
}

export interface PickRow {
  allocation_id: number;
  request_id: number;
  request_number: string;
  reseller_id: number;
  reseller_name: string | null;
  location_id: number;
  location_code: string | null;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  warehouse_location_id: number;
  open_qty: number;
  priority: string;
  ready?: boolean;   // picked and packed on the request (1.11)
}

export interface Proposal {
  request_id: number;
  request_number: string;
  reseller_id: number;
  reseller_name: string | null;
  location_id: number;
  location_code: string | null;
  product_id: number;
  sku: string | null;
  priority: string;
  created_at: string;
  awaiting_supply: number;
  proposed_qty: number;
}

export interface LinkedReq {
  id: number;
  number: string;
  status: string;
  qty_required: number;
  qty_outstanding: number;
  qty_awaiting_supply: number;
}

export interface Transfer {
  id: number;
  number: string;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  quantity: number;
  destination_location_id: number | null;   // null when hidden from a reseller user
  destination_location_code: string | null;
  destination_reseller_id: number | null;
  destination_reseller_name: string | null;
  source_location_id: number | null;
  source_location_code: string | null;
  source_reseller_id: number | null;
  source_reseller_name: string | null;
  /** DIRECT, or VIA_WAREHOUSE: received and checked at the warehouse before the rep delivers it. */
  route?: "DIRECT" | "VIA_WAREHOUSE";
  warehouse_received_at?: string | null;
  warehouse_received_by?: string | null;
  warehouse_check_notes?: string | null;
  reason: string;
  urgency: string;
  status: string;
  requested_by: string | null;
  requested_at: string;
  approved_by: string | null;
  approved_at: string | null;
  approval_notes: string | null;
  source_consent_reference: string | null;
  collected_by: string | null;
  collected_at: string | null;
  qty_collected: number;
  received_by: string | null;
  received_at: string | null;
  qty_received: number;
  qty_returned: number;
  qty_lost: number;
  qty_in_transit: number;
  destination_request: LinkedReq | null;
  source_request: LinkedReq | null;
  cancel_reason: string | null;
  notes: string | null;
  collected_by_user_id?: number | null;
  collected_by_sales_rep?: boolean;
  received_by_name?: string | null;
  receipt_notes?: string | null;
  photos?: number[];
  photos_retired?: number;
  shipping_method?: "COURIER" | "SALES_REP" | null;   // how it travels (1.11)
  carrier_reference?: string | null;
  tracking_number?: string | null;
  carried_by_user_id?: number | null;
  carried_by?: string | null;
  shipping_arranged_at?: string | null;
  shipping_arranged_by?: string | null;
  collected_from_name?: string | null;
  note_emailed_at?: string | null;
  note_email_to?: string | null;
  note_email_error?: string | null;
}

export interface SourceOption {
  location_id: number;
  location_code: string;
  location_name: string;
  reseller_id: number;
  reseller_name: string;
  account_ref: string;
  on_hand: number;
  reserved: number;
  blocked: number;
  available: number;
  transfer_consent: string;
  eligible: boolean;
  ineligible_reason: string | null;
}

export interface POLine {
  id: number;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  qty_ordered: number;
  qty_received: number;
  qty_outstanding: number;
  unit_cost: string | null;
}

export interface PurchaseOrder {
  id: number;
  number: string;
  supplier_name: string;
  supplier_reference: string | null;
  warehouse_location_id: number;
  warehouse_code: string | null;
  expected_date: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  lines: POLine[];
}

export interface GoodsReceipt {
  id: number;
  number: string;
  purchase_order_id: number | null;
  warehouse_location_id: number;
  supplier_reference: string | null;
  received_at: string;
  received_by: string | null;
  notes: string | null;
  lines: { id: number; product_id: number; sku: string | null; qty_received: number; qty_damaged: number }[];
  open_backorders_for_received_skus: number;
}

export interface StocktakeLine {
  id: number;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  expected_qty: number | null;
  expected_blocked_qty: number | null;
  counted_qty: number;
  counted_damaged_qty: number;
  variance: number | null;
  shortage: number;
  qty_sold: number;
  qty_missing: number;
  classified: boolean;
  notes: string | null;
  qty_held?: number;
}

export interface Stocktake {
  id: number;
  number: string;
  location_id: number;
  location_code: string | null;
  reseller_id: number;
  reseller_name: string | null;
  count_date: string;
  counted_by: string | null;
  status: string;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  sale_id: number | null;
  notes: string | null;
  total_variance: number;
  lines: StocktakeLine[];
  total_shortage?: number;
  confirm_due_at?: string | null;
  overdue?: boolean;
  reminder_count?: number;
  last_reminded_at?: string | null;
  confirmed_on_behalf_reason?: string | null;
  invoice_id?: number | null;
  invoice_number?: string | null;
  account_ref?: string | null;       // who and where (1.11)
  location_name?: string | null;
  location_address?: string | null;
  location_city?: string | null;
  sales_rep?: string | null;
  find_days?: number | null;          // the find window (1.11, D3)
  recheck_requested_at?: string | null;
  recheck_requested_by?: string | null;
  recheck_note?: string | null;
  disputed_at?: string | null;
  disputed_by?: string | null;
  dispute_note?: string | null;
  recount_of_id?: number | null;
  recount_of_number?: string | null;
  superseded_by_id?: number | null;
  superseded_by_number?: string | null;
}

export interface InvoiceLine {
  id: number;
  sale_line_id: number;
  sale_number: string;
  sale_date: string;
  location_code: string;
  sku: string;
  description: string;
  quantity: number;
  unit_price: string;
  tax_code: string;
  tax_rate: string;
  line_net: string;
  line_tax: string;
  line_total: string;
  is_active: boolean;
}

export interface Invoice {
  id: number;
  number: string;
  reseller_id: number;
  status: string;
  invoice_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  total: string;
  bill_to_name: string;
  bill_to_account_ref: string;
  bill_to_address: string | null;
  bill_to_tax_number: string | null;
  issuer_name: string;
  issuer_details: string;
  external_reference: string | null;
  exported_at: string | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  issued_by: string | null;
  issued_at: string | null;
  voided_by: string | null;
  voided_at: string | null;
  void_reason: string | null;
  lines: InvoiceLine[];
  xero_reference?: string | null;      // RM/FM/Admin only (D12)
  xero_recorded_by?: string | null;
  xero_recorded_at?: string | null;
}

export interface UninvoicedLine {
  sale_line_id: number;
  sale_id: number;
  sale_number: string;
  sale_date: string;
  reseller_id: number;
  reseller_name: string | null;
  location_code: string | null;
  product_id: number;
  sku: string | null;
  quantity: number;
  unit_price: string;
  tax_code: string;
  line_net: string;
  age_days: number;
}

export interface Dashboard {
  warehouse: { on_hand: number; reserved: number; blocked: number; available: number } | null;
  consignment: { on_hand: number; available: number };
  in_transit: number | null;
  backorders: { requests: number; qty_awaiting_supply: number; qty_outstanding: number };
  awaiting_dispatch_qty: number;
  open_deliveries: number;
  transfers_in_progress: { count: number; awaiting_approval: number; in_transit: number; discrepancies: number };
  sales_awaiting_invoicing: { qty: number; value: string };
  replenishment_attention: {
    count: number;
    items: { request_id: number; number: string; reseller_id: number; priority: string; qty_awaiting_supply: number;
      age_days: number; expected_date: string | null }[];
  };
}

export interface AuditEvent {
  id: number;
  occurred_at: string;
  actor_user_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  reseller_id: number | null;
  summary: string;
}

// ---------------------------------------------------------------------------
// Consignment stock requests
// ---------------------------------------------------------------------------

export type StockRequestStatus =
  | "DRAFT" | "SUBMITTED" | "UNDER_REVIEW" | "APPROVED" | "PARTIALLY_APPROVED" | "REJECTED"
  | "READY_FOR_SHIPMENT" | "SHIPPED" | "DELIVERED" | "CANCELLED";

export interface StockRequest {
  id: number;
  number: string;
  reseller_id: number;
  reseller_name: string | null;
  location_id: number;
  location_code: string | null;
  status: StockRequestStatus;
  decision: StockRequestStatus | null;
  priority: string;
  required_date: string | null;
  notes: string | null;
  shipping_address: string | null;
  created_by: string | null;
  created_by_user_id: number;
  created_by_role: RoleCode;
  created_at: string;
  submitted_at: string | null;
  reviewed_by: string | null;
  reviewed_by_role: RoleCode | null;
  reviewed_at: string | null;
  review_notes: string | null;
  ready_at: string | null;
  closed_at: string | null;
  line_count: number;
  qty_requested: number;
  qty_approved: number;
  qty_rejected: number;
  qty_backordered: number;
  qty_reserved: number;
  qty_shipped: number;
  qty_delivered: number;
  /** Waiting for a Relationship Manager (staff only). */
  escalated_to_user_id?: number | null;
  escalated_to?: string | null;
  escalated_by?: string | null;
  escalated_at?: string | null;
  escalation_note?: string | null;
}

export interface StockRequestLine {
  id: number;
  line_no: number;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  product_active: boolean;
  qty_requested: number;
  qty_approved: number;
  qty_rejected: number;
  qty_backordered: number;
  qty_released: number;
  qty_reserved: number;
  qty_in_transit: number;
  qty_shipped: number;
  qty_delivered: number;
  qty_backorder_open: number;
  notes: string | null;
  decision_notes: string | null;
  replenishment_request_id: number | null;
  replenishment_number: string | null;
  warehouse_available: number | null;
  first_supply?: boolean;
  find_for_me?: boolean;
  qty_arranging?: number;   // being arranged from another dealer ("Get this tyre for me")
  arranging_transfer_id?: number | null;
  arranging_transfer_number?: string | null;
  /** Staff only: already held by this dealer (this shop / all shops). */
  dealer_on_hand?: number | null;
  dealer_on_hand_all?: number | null;
  /** Transfers from another dealer covering this line's backorder (staff only). */
  covering_transfers?: { id: number; number: string; status: string; quantity: number }[];
}

export interface StockRequestEvent {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string | null;
  summary: string;
  details: Record<string, unknown> | null;
  actor_name: string | null;
  actor_role: RoleCode | null;
  occurred_at: string;
}

export interface StockRequestDetail extends StockRequest {
  lines: StockRequestLine[];
  events: StockRequestEvent[];
  shipments: Delivery[];
  /** Staff only. */
  approval_method?: string | null;
  approval_contact?: string | null;
  approval_comments?: string | null;
}

export interface StockRequestSummary {
  by_status: Record<StockRequestStatus, number>;
  pending_approval: number;
  to_ship: number;
  in_transit: number;
  my_open: number;
}

export interface InventoryOverviewRow {
  product_id: number;
  sku: string;
  product_name: string;
  is_active: boolean;
  warehouse_on_hand: number;
  blocked: number;
  reserved: number;
  shipped: number;
  total: number;
  available: number;
  delivered: number;
  requested_pending: number;
}

export interface StockAllocationRow {
  allocation_id: number;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  reseller_id: number;
  reseller_name: string | null;
  location_code: string | null;
  quantity: number;
  open_qty: number;
  replenishment_request_id: number;
  replenishment_number: string;
  stock_request_id: number | null;
  stock_request_number: string | null;
  created_at: string;
}

export interface AppNotification {
  id: number;
  title: string;
  body: string | null;
  link: string | null;
  entity_type: string | null;
  entity_id: number | null;
  read_at: string | null;
  created_at: string;
}

/** A website stock API key (Admin → Website access). The full key is only in the create response. */
export interface PartnerKey {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
  created_by: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  key?: string;
}

/** Dealer history at a glance (GET /resellers/{id}/history-summary, staff only). */
export interface DealerHistory {
  reseller_id: number;
  onboarded_at: string;
  onboarded_by: string | null;
  dealer_type: "EXISTING" | "NEW";
  first_stock: { occurred_at: string; transaction_number: string; txn_type: string; reference_number: string | null } | null;
  onboarding_stock_kind: "INITIAL_STOCK" | "FIRST_DELIVERY" | null;
  onboarding_stock_at: string | null;
  /** quantity = after any initial stock corrections; recorded = as first entered, when a correction changed it. */
  onboarding_stock: { product_id: number; sku: string; name: string; quantity: number; recorded?: number | null }[];
  units_sold: number;
  sales_count: number;
  last_sale: { id: number; number: string; sale_date: string; units: number } | null;
  corrections?: number;
}

export interface InitialStockCorrection {
  transaction_id: number;
  transaction_number: string;
  corrected_at: string;
  corrected_by: string | null;
  reason: string;
  changes: { product_id: number; sku: string; name: string; before: number; after: number }[];
}

/** A dealer's initial stock entry and its corrections (Relationship Manager and Administrator). */
export interface InitialStockEntry {
  transaction_id: number;
  transaction_number: string;
  recorded_at: string;
  recorded_by: string | null;
  location_id: number;
  location_code: string;
  location_name: string;
  lines: { product_id: number; sku: string; name: string; recorded: number; current: number; free_now: number }[];
  corrections: InitialStockCorrection[];
  can_correct: boolean;
  locked_reason: string | null;
  correctable_until: string | null;
}

export interface StockCorrectionRow {
  corrected_at: string;
  transaction_number: string | null;
  corrects: string | null;
  reseller_id: number | null;
  reseller_name: string | null;
  location_code: string | null;
  sku: string;
  before: number;
  after: number;
  change: number;
  corrected_by: string | null;
  reason: string | null;
}
