"""Roles and permissions. The single source of truth for backend authorisation."""

from enum import StrEnum


class Role(StrEnum):
    """Pilot profiles: an Administrator (super user) and four business roles (see docs/PILOT_USERS.md)."""

    ADMINISTRATOR = "ADMINISTRATOR"
    RELATIONSHIP_MANAGER = "RELATIONSHIP_MANAGER"
    WAREHOUSE_MANAGER = "WAREHOUSE_MANAGER"
    SALES_REP = "SALES_REP"
    RESELLER = "RESELLER"
    FINANCE_MANAGER = "FINANCE_MANAGER"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMINISTRATOR: "Administrator",
    Role.RELATIONSHIP_MANAGER: "Relationship Manager",
    Role.WAREHOUSE_MANAGER: "Warehouse Manager",
    Role.SALES_REP: "Sales Representative",
    Role.RESELLER: "Dealer",
    Role.FINANCE_MANAGER: "Finance Manager",
}


class P(StrEnum):
    """Permission codes."""

    CATALOGUE_READ = "catalogue.read"
    CATALOGUE_WRITE = "catalogue.write"
    CATALOGUE_CREATE = "catalogue.create"   # add a product one at a time (no editing of existing products)
    CATALOGUE_IMPORT = "catalogue.import"
    COST_READ = "catalogue.cost_read"
    RESELLER_READ = "reseller.read"
    RESELLER_WRITE = "reseller.write"
    LOCATION_MANAGE = "location.manage"
    PRICING_WRITE = "pricing.write"
    ALLOCATION_WRITE = "allocation.write"
    INVENTORY_READ = "inventory.read"
    INVENTORY_RECEIVE = "inventory.receive"
    INVENTORY_ADJUST = "inventory.adjust"
    INVENTORY_BLOCK = "inventory.block"
    PURCHASING_MANAGE = "purchasing.manage"
    SALES_RECORD = "sales.record"
    SALES_REVERSE = "sales.reverse"
    SALES_CASH = "sales.cash"   # walk-in cash sale from warehouse stock
    REPLENISHMENT_READ = "replenishment.read"
    REPLENISHMENT_MANAGE = "replenishment.manage"
    REPLENISHMENT_CANCEL = "replenishment.cancel"
    REPLENISHMENT_OVERRIDE = "replenishment.override"
    REPLENISHMENT_APPROVE = "replenishment.approve"   # approve, send to the RM or reject a dealer or rep request
    REPLENISHMENT_REQUEST = "replenishment.request"
    DISPATCH = "replenishment.dispatch"
    DELIVERY_CONFIRM = "delivery.confirm"
    TRANSFER_READ = "transfer.read"
    TRANSFER_REQUEST = "transfer.request"
    TRANSFER_APPROVE = "transfer.approve"
    TRANSFER_EXECUTE = "transfer.execute"
    STOCKTAKE_RECORD = "stocktake.record"
    STOCKTAKE_APPROVE = "stocktake.approve"
    STOCKTAKE_CONFIRM = "stocktake.confirm"   # reseller confirms stock-check shortages as sold or missing
    INVOICE_READ = "invoice.read"
    INVOICE_CREATE = "invoice.create"
    INVOICE_VOID = "invoice.void"
    INVOICE_REFERENCE_READ = "invoice.reference_read"   # see invoice numbers and Xero transaction numbers on sales
    REPORT_READ = "report.read"
    AUDIT_READ = "audit.read"
    USER_MANAGE = "user.manage"
    FEEDBACK_SUBMIT = "feedback.submit"
    SETTINGS_MANAGE = "settings.manage"   # app settings, e.g. drop-off photo archiving
    PARTNER_KEYS_MANAGE = "partner_keys.manage"   # website stock API keys (Administrators only)
    DEALER_HISTORY_READ = "dealer_history.read"   # dealer history summary (Warehouse and Relationship Managers)
    INITIAL_STOCK_CORRECT = "initial_stock.correct"   # fix a dealer's wrongly entered initial stock (RM and Admin only)
    RESELLER_INITIAL_STOCK = "reseller.initial_stock"   # stock an existing reseller already holds when added
    # Consignment stock requests (multi-SKU requests with a Central Team approval stage).
    STOCK_REQUEST_READ = "stock_request.read"
    STOCK_REQUEST_CREATE = "stock_request.create"
    STOCK_REQUEST_APPROVE = "stock_request.approve"   # Central Team: review, (partially) approve, reject, reserve, release
    STOCK_REQUEST_FULFIL = "stock_request.fulfil"     # mark ready for shipment and ship


# Broad operational authority over stock, supply and fulfilment. Not an administrator (the Relationship Manager is).
_WM: frozenset[P] = frozenset({
    P.CATALOGUE_READ, P.CATALOGUE_WRITE, P.CATALOGUE_CREATE, P.CATALOGUE_IMPORT, P.COST_READ, P.RESELLER_READ,
    P.LOCATION_MANAGE, P.INVENTORY_READ,
    P.INVENTORY_RECEIVE, P.INVENTORY_ADJUST, P.INVENTORY_BLOCK, P.PURCHASING_MANAGE,
    P.REPLENISHMENT_READ, P.REPLENISHMENT_MANAGE, P.REPLENISHMENT_CANCEL, P.REPLENISHMENT_OVERRIDE,
    P.REPLENISHMENT_APPROVE, P.REPLENISHMENT_REQUEST, P.DISPATCH, P.DELIVERY_CONFIRM, P.TRANSFER_READ, P.TRANSFER_REQUEST,
    P.TRANSFER_APPROVE, P.TRANSFER_EXECUTE, P.STOCKTAKE_RECORD, P.STOCKTAKE_APPROVE, P.REPORT_READ,
    P.FEEDBACK_SUBMIT,
    P.STOCK_REQUEST_READ, P.STOCK_REQUEST_CREATE, P.STOCK_REQUEST_APPROVE, P.STOCK_REQUEST_FULFIL,
    P.RESELLER_INITIAL_STOCK, P.SALES_CASH, P.DEALER_HISTORY_READ,
})

ROLE_PERMISSIONS: dict[Role, frozenset[P]] = {
    # Super user: every permission, including managing other administrators.
    Role.ADMINISTRATOR: frozenset(P),
    # The Relationship Manager heads the business: everything the Warehouse Manager can do (built from the same set,
    # so the two cannot drift apart), plus dealers, prices, sales, invoicing and administration.
    Role.RELATIONSHIP_MANAGER: _WM | frozenset({
        P.RESELLER_WRITE, P.PRICING_WRITE, P.ALLOCATION_WRITE, P.SALES_RECORD, P.SALES_REVERSE,
        P.INVOICE_READ, P.INVOICE_CREATE, P.INVOICE_VOID, P.INVOICE_REFERENCE_READ, P.SETTINGS_MANAGE,
        # The Relationship Manager owns the system: user logins, the change history and tester feedback are theirs.
        P.USER_MANAGE, P.AUDIT_READ,
        # Correcting a dealer's wrongly entered initial stock is the Relationship Manager's call, not the warehouse's.
        P.INITIAL_STOCK_CORRECT,
    }),
    Role.WAREHOUSE_MANAGER: _WM,
    # Invoicing and Xero numbers, with read-only sales, dealers and reports. No stock actions (FM ⊆ RM).
    Role.FINANCE_MANAGER: frozenset({
        P.CATALOGUE_READ, P.RESELLER_READ, P.INVENTORY_READ, P.REPORT_READ, P.INVOICE_READ, P.INVOICE_CREATE,
        P.INVOICE_VOID, P.INVOICE_REFERENCE_READ, P.FEEDBACK_SUBMIT,
    }),
    # Field role at reseller sites: stocktakes, reported sales, replenishment and transfer requests.
    Role.SALES_REP: frozenset({
        P.CATALOGUE_READ, P.RESELLER_READ, P.INVENTORY_READ, P.SALES_RECORD, P.STOCKTAKE_RECORD,
        P.REPLENISHMENT_READ, P.REPLENISHMENT_MANAGE, P.REPLENISHMENT_REQUEST, P.DELIVERY_CONFIRM,
        P.TRANSFER_READ, P.TRANSFER_REQUEST, P.TRANSFER_EXECUTE, P.REPORT_READ, P.FEEDBACK_SUBMIT,
        P.STOCK_REQUEST_READ, P.STOCK_REQUEST_CREATE,
    }),
    # Reseller users: always scoped to their own reseller (A-012). They may report their own sales
    # and request replenishment within their uncovered target shortfall, raise stock requests for approval
    # and confirm receipt of deliveries to their own locations.
    Role.RESELLER: frozenset({
        P.CATALOGUE_READ, P.INVENTORY_READ, P.SALES_RECORD, P.REPLENISHMENT_READ, P.REPLENISHMENT_REQUEST,
        P.DELIVERY_CONFIRM, P.TRANSFER_READ, P.INVOICE_READ, P.REPORT_READ, P.FEEDBACK_SUBMIT,
        P.STOCK_REQUEST_READ, P.STOCK_REQUEST_CREATE, P.STOCKTAKE_CONFIRM,
    }),
}

STAFF_ROLES = frozenset({Role.ADMINISTRATOR, Role.RELATIONSHIP_MANAGER, Role.WAREHOUSE_MANAGER, Role.SALES_REP,
                         Role.FINANCE_MANAGER})


def role_has(role: Role | str, permission: P) -> bool:
    return permission in ROLE_PERMISSIONS[Role(role)]
