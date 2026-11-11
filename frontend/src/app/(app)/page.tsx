"use client";

import { AdministratorDashboard } from "@/components/dashboards/AdministratorDashboard";
import { FinanceDashboard } from "@/components/dashboards/FinanceDashboard";
import { RelationshipManagerDashboard } from "@/components/dashboards/RelationshipManagerDashboard";
import { ResellerDashboard } from "@/components/dashboards/ResellerDashboard";
import { SalesRepresentativeDashboard } from "@/components/dashboards/SalesRepresentativeDashboard";
import { WarehouseManagerDashboard } from "@/components/dashboards/WarehouseManagerDashboard";
import { useAuth } from "@/lib/auth";

/** Each pilot role gets a dashboard designed around its own workflow. */
export default function DashboardPage() {
  const { user } = useAuth();
  switch (user?.role) {
    case "ADMINISTRATOR":
      return <AdministratorDashboard />;
    case "RELATIONSHIP_MANAGER":
      return <RelationshipManagerDashboard />;
    case "WAREHOUSE_MANAGER":
      return <WarehouseManagerDashboard />;
    case "SALES_REP":
      return <SalesRepresentativeDashboard />;
    case "RESELLER":
      return <ResellerDashboard />;
    case "FINANCE_MANAGER":
      return <FinanceDashboard />;
    default:
      return null;
  }
}
