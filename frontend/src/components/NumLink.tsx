"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

/** A number that opens the screen explaining it (staff only; dealers see the plain number). */
export function NumLink({ href, children, title }: { href: string | null | undefined; children: ReactNode; title?: string }) {
  const { user } = useAuth();
  if (!href || !user || user.reseller_id) return <>{children}</>;
  return (
    <Link href={href} title={title} onClick={(e) => e.stopPropagation()}
      className="-mx-1 rounded px-1 underline decoration-line-strong decoration-dotted underline-offset-4 hover:bg-subtle hover:decoration-ink">
      {children}
    </Link>
  );
}

/** Shown at the top of a list opened from a clicked number: what it is filtered to, and a way back to everything. */
export function FilteredTo({ label, clearHref }: { label: ReactNode; clearHref: string }) {
  const router = useRouter();
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-control border border-line bg-brand-soft px-3 py-2 text-label">
      <span className="text-ink-secondary">Showing</span> <b className="font-medium text-ink">{label}</b>
      <button type="button" className="ml-auto text-ink-secondary underline underline-offset-4 hover:text-ink" onClick={() => router.replace(clearHref)}>Show all</button>
    </div>
  );
}

const qs = (params: Record<string, string | number | null | undefined>) =>
  Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");

/** Where each kind of number leads. */
export const links = {
  movements: (productId?: number | null, locationId?: number | null) => `/inventory/movement?${qs({ product_id: productId, location_id: locationId || null })}`,
  reserved: (productId?: number | null) => `/inventory/allocation?${qs({ product_id: productId })}`,
  incoming: (sku?: string | null) => `/purchasing?${qs({ q: sku })}`,
  demand: (productId?: number | null, resellerId?: number | null) => `/backorders?${qs({ product_id: productId, reseller: resellerId })}`,
  whereIs: (productId?: number | null) => `/stock-check?${qs({ product_id: productId })}`,
  atDealers: (sku?: string | null) => `/consignment?${qs({ sku })}`,
  deliveries: () => "/replenishment?tab=deliveries",
  pendingRequests: () => "/stock-requests/pending",
};
