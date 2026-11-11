/**
 * Role-specific navigation. Each pilot role sees only the modules it uses; the backend enforces the
 * same rules independently (hiding a link is never the security boundary).
 */
import {
  ArrowLeftRight, Boxes, Building2, ChartColumn, CheckCheck, ClipboardCheck, ClipboardList, FilePlus2, History, Hourglass,
  LayoutDashboard, List, Lock, Package, PackageCheck, PackageSearch, ReceiptText, SlidersHorizontal, RefreshCw, Settings, ShoppingCart, Store, Truck, UserRound,
  Warehouse, type LucideIcon,
} from "lucide-react";
import type { RoleCode } from "@/lib/types";
import { vocab } from "@/lib/terms";

export const ROLE_LABELS: Record<RoleCode, string> = {
  ADMINISTRATOR: "Administrator",
  RELATIONSHIP_MANAGER: "Relationship Manager",
  WAREHOUSE_MANAGER: "Warehouse Manager",
  SALES_REP: "Sales Representative",
  get RESELLER() { return vocab.Partner; },
  FINANCE_MANAGER: "Finance Manager",
};

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown only if the user also holds this permission (defence in depth for UI only). */
  permission?: string;
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

const dashboard: NavItem = { href: "/", label: "Dashboard", icon: LayoutDashboard };
const products: NavItem = { href: "/products", label: "Products", icon: Package, permission: "catalogue.read" };
const warehouse: NavItem = { href: "/warehouse", label: "Warehouse", icon: Warehouse, permission: "inventory.read" };
const consignment: NavItem = { href: "/consignment", label: "Consignment Stock", icon: Store, permission: "inventory.read" };
const resellers: NavItem = { href: "/resellers", get label() { return vocab.Partners; }, icon: Building2, permission: "reseller.read" };
const sales: NavItem = { href: "/sales", label: "Sales & Stocktakes", icon: ClipboardCheck, permission: "inventory.read" };
const replenishment: NavItem = { href: "/replenishment", label: "Replenishment", icon: RefreshCw, permission: "replenishment.read" };
const backorders: NavItem = { href: "/backorders", label: "Backorders", icon: Hourglass, permission: "replenishment.read" };
const transfers: NavItem = { href: "/transfers", label: "Stock Transfers", icon: ArrowLeftRight, permission: "transfer.read" };
const purchasing: NavItem = { href: "/purchasing", label: "Purchasing & Shipments", icon: Truck, permission: "purchasing.manage" };
const invoices: NavItem = { href: "/invoices", label: "Invoices", icon: ReceiptText, permission: "invoice.read" };
const reports: NavItem = { href: "/reports", label: "Reports", icon: ChartColumn, permission: "report.read" };
const settings: NavItem = { href: "/settings", label: "Settings", icon: SlidersHorizontal, permission: "settings.manage" };
const admin: NavItem = { href: "/admin", label: "Administration", icon: Settings, permission: "user.manage" };
// Inventory views and consignment stock requests (approval workflow).
const stockOverview: NavItem = { href: "/inventory", label: "Stock Overview", icon: Boxes, permission: "inventory.read" };
const stockAllocation: NavItem = { href: "/inventory/allocation", label: "Stock Allocation", icon: Lock, permission: "inventory.read" };
// Where a tyre is (warehouse and each dealer): staff and Sales Reps only, never dealers.
const checkStock: NavItem = { href: "/stock-check", label: "Check Stock", icon: PackageSearch, permission: "transfer.request" };
const stockMovement: NavItem = { href: "/inventory/movement", label: "Stock Movement", icon: History, permission: "inventory.read" };
const myRequests: NavItem = { href: "/stock-requests", label: "My Requests", icon: ClipboardList, permission: "stock_request.read" };
const createRequest: NavItem = { href: "/stock-requests/new", label: "Create Request", icon: FilePlus2, permission: "stock_request.create" };
const pendingApproval: NavItem = { href: "/stock-requests/pending", label: "Pending Approval", icon: ClipboardCheck, permission: "stock_request.approve" };
const approvedRequests: NavItem = { href: "/stock-requests/approved", label: "Approved Requests", icon: CheckCheck, permission: "stock_request.read" };
const shipments: NavItem = { href: "/stock-requests/shipments", label: "Shipments", icon: PackageCheck, permission: "stock_request.read" };
const allRequests: NavItem = { href: "/stock-requests/all", label: "All Requests", icon: List, permission: "stock_request.read" };

export function navFor(role: RoleCode, resellerId: number | null): NavGroup[] {
  switch (role) {
    case "ADMINISTRATOR":
      return [
        { group: "Overview", items: [dashboard] },
        { group: "Inventory", items: [stockOverview, checkStock, stockAllocation, stockMovement, products, warehouse, consignment] },
        { group: "Consignment", items: [pendingApproval, approvedRequests, shipments, allRequests, myRequests, createRequest] },
        { group: "Customers", items: [resellers, sales] },
        { group: "Operations", items: [replenishment, backorders, transfers, purchasing] },
        { group: "Commercial", items: [invoices] },
        { group: "Insights", items: [reports] },
        { group: "System", items: [admin, settings] },
      ];
    case "RELATIONSHIP_MANAGER":
      return [
        { group: "Overview", items: [dashboard] },
        { group: "Consignment", items: [pendingApproval, approvedRequests, shipments, allRequests, myRequests, createRequest] },
        { group: "Customers", items: [resellers, consignment, sales] },
        { group: "Operations", items: [replenishment, backorders, transfers, purchasing] },
        { group: "Inventory", items: [stockOverview, checkStock, stockAllocation, stockMovement, warehouse] },
        { group: "Catalogue", items: [products] },
        { group: "Commercial", items: [invoices] },
        { group: "Insights", items: [reports] },
        { group: "System", items: [admin, settings] },
      ];
    case "WAREHOUSE_MANAGER":
      return [
        { group: "Overview", items: [dashboard] },
        { group: "Inventory", items: [stockOverview, checkStock, stockAllocation, stockMovement, products, warehouse, consignment] },
        { group: "Consignment", items: [pendingApproval, approvedRequests, shipments, allRequests, myRequests, createRequest] },
        { group: "Operations", items: [replenishment, backorders, transfers, purchasing, { ...sales, label: "Stocktakes & Sales" }] },
        { group: "Insights", items: [reports] },
      ];
    case "SALES_REP":
      return [
        { group: "Overview", items: [dashboard] },
        { group: "Consignment", items: [myRequests, createRequest, approvedRequests, shipments, allRequests] },
        { group: "Customers", items: [resellers, consignment, sales] },
        { group: "Operations", items: [replenishment, backorders, transfers] },
        { group: "Inventory", items: [stockOverview, checkStock] },
      ];
    case "FINANCE_MANAGER":
      return [
        { group: "Overview", items: [dashboard] },
        { group: "Commercial", items: [invoices, { ...sales, label: "Sales" }] },
        { group: "Customers", items: [resellers] },
        { group: "Insights", items: [reports] },
      ];
    case "RESELLER":
      return [
        { group: "Overview", items: [{ ...dashboard, label: "My Dashboard" }] },
        { group: "My Stock", items: [consignment] },
        { group: "Actions", items: [
          { href: "/sales", label: "Report Sale", icon: ShoppingCart, permission: "sales.record" },
          { href: "/my-sales", label: "My Sales", icon: ChartColumn, permission: "inventory.read" },
          { ...createRequest, label: "Request Stock" },
        ] },
        { group: "Tracking", items: [
          myRequests,
          { ...backorders, label: "Backorders" },
          { href: "/replenishment?tab=deliveries", label: "Deliveries", icon: Truck, permission: "replenishment.read" },
          transfers,
          ...(resellerId ? [{ href: `/resellers/${resellerId}`, label: "My account", icon: UserRound }] : []),
        ] },
        { group: "Commercial", items: [invoices] },
      ];
  }
}
