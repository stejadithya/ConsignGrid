# Stock allocation & consignment requests

Introduced in **v1.3.0**. Decisions: `DECISION_LOG.md` P-008 – P-016; approval details, escalation and the kind message in v1.11.0 (P-034 – P-037).

## Workflow

```
DRAFT → SUBMITTED → UNDER REVIEW → APPROVED / PARTIALLY APPROVED / REJECTED
                                   → READY FOR SHIPMENT → SHIPPED → DELIVERED
DRAFT / SUBMITTED / UNDER REVIEW → CANCELLED (by the requester or the Central Team)
```

| Step | Who | What happens |
|---|---|---|
| Create (draft) | Reseller (own account), Sales Rep (any reseller), RM, WM, Administrator | Multi-SKU request with a quantity, notes per line, a required date, a priority and a shipping address. The requester and their **role** are recorded. |
| Submit | The requester, or a user of the same reseller | Validated again. The Central Team is notified. **Nothing is reserved.** |
| Review | Central Team (RM, WM, Administrator) | Optional "Start review" moves the request to UNDER REVIEW. **Print pick sheet** (tyres, quantities, shop and delivery address, no prices) is available while the request is under review and until it ships. |
| Send to RM (1.11) | Warehouse Manager | **Send to Relationship Manager** with an optional note. The request waits for that RM: only they (or an Administrator) can approve or reject it; they can **Hand back to warehouse**. The warehouse carries on after approval. |
| Decide | Central Team | For each line: the approved quantity (≤ warehouse available) is **reserved immediately**. The remainder is either **backordered** or **rejected**. The outcome is Approved, Partially approved or Rejected. The dialog shows how many of the tyre the dealer already holds. When anything is approved or backordered, a second step asks for the **approval details**: who (the signed-in user), how (phone, in person, email, text/WhatsApp, standard approval), who they spoke to (not needed for a standard approval) and comments. These are shown to staff only. |
| Reserve / release | Central Team | **Reserve** puts newly available stock against a backordered line (backordered → approved). **Release** returns reserved, unshipped stock to availability. The quantity is then either cancelled or kept on backorder. |
| Ready for shipment | Warehouse Manager | Marks the stock as picked and packed. |
| Ship | Warehouse Manager | Creates a shipment (delivery) with carrier, tracking number, address and notes. It ships reserved quantities only (shipped ≤ approved), so nothing can ship before approval. Stock moves from the warehouse to in transit. |
| Confirm delivery | Reseller (own), Sales Rep, RM, WM | Records the delivery date, reference, quantities received (≤ shipped) and notes. Received stock moves into the reseller's consignment stock. A short quantity stays in transit until the warehouse resolves it. |

**Anything not supplied** (a rejected request, or the rejected part of a partial approval): the dealer sees the standard kind message, never the internal reason: "Sorry, we couldn't deliver your order this time, but we're working on it. Please feel free to call us, or let us know when we can call you." It is on the request, in a notification and on the dealer's **Messages** card. Dealers see "Not available right now" instead of "Rejected". **Please call me** (the dealer or a sales rep) records a preferred time and phone number and tells the Relationship Managers and the dealer's rep.

Backordered quantities show on the existing **Backorders** page, and the allocation proposal can reserve them. The stock request updates automatically either way.

## How it fits the existing design

Each approved line creates one replenishment request with reason `STOCK_REQUEST`. Reservation, dispatch, receipt and discrepancy resolution are the existing replenishment functions, posted through the inventory ledger. The stock request status is derived from those quantities. Existing Replenishment, Backorders, Pick & dispatch and Deliveries screens continue to work and show these requests too.

## Inventory views

* **Stock overview** (`/inventory`), per SKU:
  * Total = warehouse on hand + shipped (in transit).
  * Available = Total − Reserved − Shipped (− Blocked).
  * Also shows Delivered (at resellers on consignment) and quantity awaiting approval.
* **Stock allocation** (`/inventory/allocation`) shows warehouse stock reserved for resellers, linked to its stock request.
* **Stock movement** (`/inventory/movement`) shows the ledger, filterable by location and SKU.

## Validations

* Quantity is a whole number greater than 0 and no more than `STOCK_REQUEST_MAX_LINE_QTY` (500).
* A request has at most `STOCK_REQUEST_MAX_LINES` (50) SKUs, and each SKU appears once.
* The SKU must be active. The reseller account and its location must be active, both when the request is submitted and when it is approved.
* The required date cannot be in the past. Resellers cannot set Urgent priority.
* Approved ≤ warehouse available, shipped ≤ reserved (approved), and delivered ≤ shipped. Nothing ships before approval.
* Reseller users only ever see their own requests, shipments and notifications. Drafts are visible only to the requester's side.

## Audit and notifications

Every action is written to the request history and to the audit log (`stock_request.*`). Each entry records the user, role, action, from/to status and quantities. In-app notifications (the bell) go to:

| Event | Recipients |
|---|---|
| Submitted | The Central Team |
| Sent to a Relationship Manager / handed back | That RM / the Warehouse Manager who sent it |
| Decided | The requester, the reseller's users and the assigned sales rep (the dealer's users get the kind message when anything is not supplied; the rep gets the summary) |
| Please call me | The Relationship Managers and the dealer's sales rep |
| Approved with stock | The warehouse |
| Ready, shipped or released | The requester's side |
| Delivered | The requester, the approver and the shipper |

## API (`/api/stock-requests`)

| Method | Path | Purpose |
|---|---|---|
| GET | `?view=mine\|pending\|approved\|shipments\|all` | List requests |
| POST | `` | Create (`submit: true` to submit at once) |
| GET / PUT | `/{id}` | Detail, or edit a draft |
| POST | `/{id}/submit`, `/{id}/cancel`, `/{id}/review` | Lifecycle steps |
| POST | `/{id}/decision`, `/{id}/reject` | Approval (`decision` takes `approval {method, contact, comments}` when anything is approved or backordered) |
| POST | `/{id}/escalate`, `/{id}/hand-back` | Send to a Relationship Manager, and hand back (1.11) |
| POST | `/{id}/callback` | "Please call me" (dealer or sales rep; 1.11) |
| POST | `/{id}/lines/{line}/reserve`, `/{id}/lines/{line}/release` | Reservations |
| POST | `/{id}/ready`, `/{id}/ship` | Fulfilment |
| POST | `/{id}/shipments/{delivery}/confirm` | Delivery confirmation |
| GET | `/summary` | Dashboard counts |
| GET | `/inventory/overview`, `/inventory/allocations` | Inventory views |

Notifications: `GET /api/notifications` (`?after_id=` for only newer ones), `GET /api/notifications/unread-count` (also returns `latest_id`), `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`. New notifications pop up with a short sound (P-045).

Replenishment requests raised by dealers and reps have the same approval details, escalation, kind rejection, ready and ship steps on the request itself: `POST /api/replenishment/requests/{id}/approve|escalate|hand-back|reject|ready|ship` (P-037). Lines created by a stock request are managed here, on the stock request (those endpoints return 409 "Managed on SRQ-…").
