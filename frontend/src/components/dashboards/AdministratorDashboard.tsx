"use client";

import {
  ClipboardList, FileSpreadsheet, MessageSquare, Scale, Store, Users, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { ROLE_LABELS } from "@/config/roles";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Dashboard, Product, RoleCode, UserOut } from "@/lib/types";
import { Alert, Badge, Card, EmptyState, IconChip, Loading } from "../ui";
import { DashboardHeader, plural, RoleBanner, Section } from "./shared";
import { StockRequestsPanel } from "./StockRequestsPanel";
import { branding } from "@/config/branding";

interface FeedbackRow { id: number; user_name: string | null; role: string; page: string; feedback_type: string; description: string; created_at: string }

const ACTIONS: { href: string; label: string; detail: string; icon: LucideIcon }[] = [
  { href: "/admin", label: "Users & roles", detail: "Add people, reset passwords", icon: Users },
  { href: "/products", label: "Import SKUs from Excel", detail: "Product master and prices", icon: FileSpreadsheet },
  { href: "/admin", label: "Pilot feedback", detail: "Issues and ideas from users", icon: MessageSquare },
  { href: "/admin", label: "Audit log & reconciliation", detail: "Who did what; ledger check", icon: Scale },
  { href: "/purchasing", label: "Purchasing & receipts", detail: "Incoming supplier stock", icon: ClipboardList },
  { href: "/resellers", label: "Dealers", detail: "Accounts, targets and prices", icon: Store },
];

/** Super-user overview: the whole network at a glance plus the administration shortcuts. */
export function AdministratorDashboard() {
  const { user } = useAuth();
  const { data: d, error } = useApi<Dashboard>("/reports/dashboard");
  const { data: users } = useApi<UserOut[]>("/users");
  const { data: products } = useApi<Product[]>("/products", { limit: 1000 });
  const { data: feedback } = useApi<FeedbackRow[]>("/feedback", { limit: 5 });
  if (!user) return null;
  const active = (users ?? []).filter((u) => u.is_active);
  const byRole = Object.entries(active.reduce<Record<string, number>>((a, u) => ({ ...a, [u.role]: (a[u.role] ?? 0) + 1 }), {}));

  return (
    <>
      <DashboardHeader name={user.full_name} subtitle={`Everything across ${branding.productName}: users, product master, stock, demand and invoicing.`} />
      <Alert>{error}</Alert>
      {!d && !error && <Loading label="Loading dashboard…" />}
      {d && (
        <>
          <RoleBanner theme="system" figures={[
            { label: "Active users", value: active.length, href: "/admin", hint: `${(users ?? []).length - active.length} switched off` },
            { label: "Products", value: (products ?? []).length, href: "/products",
              hint: products?.length ? `${products.filter((p) => p.is_active).length} active` : "Import the product master from Excel" },
            { label: "Warehouse available", value: (d.warehouse?.available ?? 0).toLocaleString(), href: "/warehouse",
              hint: `${(d.warehouse?.on_hand ?? 0).toLocaleString()} on hand · ${d.warehouse?.reserved ?? 0} reserved` },
            { label: "Waiting for supply", value: d.backorders.qty_awaiting_supply.toLocaleString(), href: "/backorders",
              hint: plural(d.backorders.requests, "open request"), tone: d.backorders.qty_awaiting_supply ? "warn" : undefined },
            { label: "Sold, not invoiced", value: d.sales_awaiting_invoicing.qty.toLocaleString(), href: "/invoices",
              hint: "Invoiced through Xero", tone: d.sales_awaiting_invoicing.qty ? "warn" : undefined },
          ]} />

          <StockRequestsPanel focus="approve" />

          <Section title="Administration">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {ACTIONS.map((a) => (
                <Link key={a.label} href={a.href} className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card transition hover:border-line-strong hover:shadow-raised focus-visible:outline-2 focus-visible:outline-ink">
                  <IconChip icon={a.icon} tone="accent" />
                  <div><div className="font-medium text-ink">{a.label}</div><div className="text-label text-ink-muted">{a.detail}</div></div>
                </Link>
              ))}
            </div>
          </Section>

          <div className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card title="Active users" padded={false} actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/admin">Manage</Link>}>
              <ul className="divide-y divide-line">
                {byRole.map(([role, n]) => (
                  <li key={role} className="flex items-center justify-between px-5 py-3 text-body">
                    <span>{ROLE_LABELS[role as RoleCode] ?? role}</span><Link className="link num font-semibold" href="/admin">{n}</Link>
                  </li>
                ))}
                {!byRole.length && <li><EmptyState compact title="No users yet" /></li>}
              </ul>
            </Card>
            <Card title="Latest pilot feedback" className="xl:col-span-2" padded={false}
              actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/admin">All feedback</Link>}>
              {feedback && feedback.length === 0 ? <EmptyState compact title="No feedback yet" description="Feedback sent from the user menu appears here." /> : (
                <ul className="divide-y divide-line">
                  {(feedback ?? []).map((f) => (
                    <li key={f.id} className="px-5 py-3">
                      <div className="flex items-center gap-2 text-label"><Badge value={f.feedback_type} tone={f.feedback_type === "ISSUE" ? "critical" : "info"} />
                        <span className="font-medium">{f.user_name}</span><span className="text-ink-muted">· {f.page}</span>
                        <time className="ml-auto text-caption text-ink-muted">{fmtDateTime(f.created_at)}</time></div>
                      <p className="mt-1 line-clamp-2 text-label text-ink-secondary">{f.description}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
