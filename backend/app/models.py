"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""

from app.core.numbering import NumberSequence  # noqa: F401
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.catalogue.models import Product, TaxRate  # noqa: F401
from app.modules.consignment.models import AllocationChange, ConsignmentAllocation  # noqa: F401
from app.modules.customers.models import (  # noqa: F401
    ConsignmentAgreement,
    CustomerPrice,
    Location,
    Reseller,
)
from app.modules.identity.models import User  # noqa: F401
from app.modules.inventory.models import (  # noqa: F401
    InventoryEntry,
    InventoryTransaction,
    StockBalance,
    StockReservation,
)
from app.modules.invoicing.models import Invoice, InvoiceLine  # noqa: F401
from app.modules.partner.models import PartnerApiKey  # noqa: F401
from app.modules.pilot.models import PilotFeedback  # noqa: F401
from app.modules.proofs.models import AppSetting, ProofPhoto  # noqa: F401
from app.modules.purchasing.models import (  # noqa: F401
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.modules.replenishment.models import (  # noqa: F401
    Delivery,
    DeliveryLine,
    ReplenishmentAllocation,
    ReplenishmentEvent,
    ReplenishmentRequest,
)
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine  # noqa: F401
from app.modules.stock_requests.models import (  # noqa: F401
    Notification,
    StockRequest,
    StockRequestEvent,
    StockRequestLine,
)
from app.modules.stocktakes.models import Stocktake, StocktakeLine  # noqa: F401
from app.modules.transfers.models import Transfer  # noqa: F401
