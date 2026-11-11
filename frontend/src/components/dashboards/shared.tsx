"use client";

/** Building blocks shared by the role dashboards. Each role composes them around its own workflow. */

import { ArrowUpRight, Briefcase, ChevronRight, MapPin, Receipt, ShieldCheck, Store, Warehouse, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { branding } from "@/config/branding";
import { fmtDateTime } from "@/lib/format";
import { cx, EmptyState, IconChip, KPI_HINT, KPI_LABEL, KPI_VALUE, PageHeader, SectionHeader, type Tone } from "../ui";

export function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

export function DashboardHeader({ name, title, subtitle, actions }: { name: string; title?: string; subtitle: string; actions?: ReactNode }) {
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  return (
    <PageHeader eyebrow={<>{branding.productName} <span className="text-line-strong">·</span> {today}</>}
      title={title ?? `${greeting()}, ${name.split(" ")[0]}`} subtitle={subtitle} actions={actions} />
  );
}

export function Section({ title, description, actions, children, className }: {
  title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={className ?? "mt-8"} aria-label={title}>
      <SectionHeader title={title} description={description} actions={actions} />
      {children}
    </section>
  );
}

export interface QueueItem { label: string; value: number | string; hint?: string; href?: string; icon: LucideIcon; tone?: Tone }

/** Compact actionable counters ("Ready to pick", "Stocktakes due"…). */
export function WorkQueue({ items }: { items: QueueItem[] }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-line bg-line shadow-card lg:grid-cols-4">
      {items.map((q) => {
        const body = (
          <div className="flex h-full items-start gap-3 bg-surface px-4 py-4 transition group-hover:bg-subtle">
            <IconChip icon={q.icon} tone={Number(q.value) > 0 ? q.tone ?? "default" : "default"} size="sm" />
            <div className="min-w-0">
              <div className="text-label font-medium text-ink-secondary">{q.label}</div>
              <div className="num text-metric-compact font-semibold text-ink">{q.value}</div>
              {q.hint && <div className={KPI_HINT}>{q.hint}</div>}
            </div>
          </div>
        );
        return q.href
          ? <Link key={q.label} href={q.href} className="group focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink">{body}</Link>
          : <div key={q.label}>{body}</div>;
      })}
    </div>
  );
}

export interface AttentionItem { key: string; tone: Tone; icon: LucideIcon; title: string; detail: string; href: string }

export function AttentionList({ items, emptyTitle = "All clear", emptyDescription, emptyIcon }: {
  items: AttentionItem[]; emptyTitle?: string; emptyDescription: string; emptyIcon?: LucideIcon;
}) {
  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
      {items.length === 0 ? (
        <EmptyState compact icon={emptyIcon} title={emptyTitle} description={emptyDescription} />
      ) : (
        <ul className="grid gap-px bg-line lg:grid-cols-2">
          {items.map((a, i) => (
            <li key={a.key} className={cx("bg-surface", i === items.length - 1 && i % 2 === 0 && "lg:col-span-2")}>
              <Link href={a.href} className="group flex items-center gap-3.5 px-5 py-4 transition hover:bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink">
                <IconChip icon={a.icon} tone={a.tone} />
                <div className="min-w-0 flex-1">
                  <div className="text-body font-medium text-ink">{a.title}</div>
                  <div className="truncate text-label text-ink-muted">{a.detail}</div>
                </div>
                <ChevronRight className="size-4 shrink-0 text-ink-muted transition group-hover:translate-x-0.5 group-hover:text-ink" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface ActivityItem { key: string; icon: LucideIcon; title: ReactNode; detail?: ReactNode; at: string; href?: string }

export function ActivityList({ items, emptyTitle, emptyDescription }: { items: ActivityItem[] | null; emptyTitle: string; emptyDescription: string }) {
  if (items && items.length === 0) return <EmptyState compact title={emptyTitle} description={emptyDescription} />;
  return (
    <ul className="divide-y divide-line">
      {(items ?? []).map((a) => {
        const inner = (
          <div className="flex items-start gap-3 px-5 py-3">
            <a.icon className="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="text-body text-ink">{a.title}</div>
              {a.detail && <div className="truncate text-caption text-ink-muted">{a.detail}</div>}
            </div>
            <time className="shrink-0 text-caption whitespace-nowrap text-ink-muted" dateTime={a.at}>{fmtDateTime(a.at)}</time>
          </div>
        );
        return <li key={a.key}>{a.href ? <Link href={a.href} className="block transition hover:bg-subtle">{inner}</Link> : inner}</li>;
      })}
    </ul>
  );
}


/** Which dashboard a banner belongs to. Roles are named in text with an icon; they are never colour-coded. */
export type RoleTheme = "owner" | "warehouse" | "field" | "dealer" | "system" | "finance";
const ROLE_LABELS: Record<RoleTheme, { label: string; icon: LucideIcon }> = {
  owner: { label: "Owner's overview", icon: Briefcase },
  warehouse: { label: "Warehouse floor", icon: Warehouse },
  field: { label: "Field day", icon: MapPin },
  dealer: { label: "My shop", icon: Store },
  system: { label: "System", icon: ShieldCheck },
  finance: { label: "Billing", icon: Receipt },
};

export interface HeadlineFigure { label: string; value: ReactNode; hint?: ReactNode; href?: string; tone?: "warn" | "danger" | "ok" }

/** The headline card at the top of a role dashboard: who it is for and the figures that matter most to that role.
 *  The same neutral card for every role; a figure is coloured only when it needs attention (or is on target). */
export function RoleBanner({ theme, figures }: { theme: RoleTheme; figures: HeadlineFigure[] }) {
  const { label, icon: Icon } = ROLE_LABELS[theme];
  const tones = { warn: "text-warning", danger: "text-danger", ok: "text-success" };
  return (
    <div className="mb-6 overflow-hidden rounded-card border border-line bg-surface shadow-card">
      <div className="px-card pt-4">
        <span className="inline-flex items-center gap-1.5 rounded-pill bg-neutral-soft px-2.5 py-0.5 text-caption font-semibold text-ink-secondary">
          <Icon className="size-3.5" aria-hidden />{label}
        </span>
      </div>
      <div className={cx("grid grid-cols-2 gap-px p-3 sm:p-4", figures.length >= 5 ? "lg:grid-cols-5" : "lg:grid-cols-4")}>
        {figures.map((f) => {
          const body = (
            <div className="h-full rounded-control px-3 py-2.5 transition group-hover:bg-subtle">
              <div className={cx(KPI_LABEL, "flex items-start gap-1")}><span className="line-clamp-2">{f.label}</span>
                {f.href && <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" aria-hidden />}</div>
              <div className={cx(KPI_VALUE, "mt-1", f.tone ? tones[f.tone] : "text-ink")}>{f.value}</div>
              {f.hint && <div className={KPI_HINT}>{f.hint}</div>}
            </div>
          );
          return f.href
            ? <Link key={f.label} href={f.href} className="group block rounded-control focus-visible:outline-2 focus-visible:outline-ink">{body}</Link>
            : <div key={f.label}>{body}</div>;
        })}
      </div>
    </div>
  );
}

export interface Job { label: string; value: number; hint?: string; href: string; icon: LucideIcon; urgent?: boolean }

/** A numbered to-do list: each job shows how many items wait and opens the screen to do it. */
export function JobList({ jobs }: { jobs: Job[] }) {
  return (
    <ol className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface shadow-card">
      {jobs.map((j, i) => (
        <li key={j.label}>
          <Link href={j.href} className="group flex items-center gap-4 px-4 py-3.5 transition hover:bg-subtle sm:px-5">
            <span className={cx("flex size-7 shrink-0 items-center justify-center rounded-full text-label font-semibold",
              j.value > 0 ? (j.urgent ? "bg-danger text-white" : "bg-ink text-white") : "bg-subtle text-ink-muted")}>{i + 1}</span>
            <j.icon className="size-4 shrink-0 text-ink-muted" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className={cx("text-body font-medium", j.value > 0 ? "text-ink" : "text-ink-muted")}>{j.label}</div>
              {j.hint && <div className="truncate text-caption text-ink-muted">{j.hint}</div>}
            </div>
            <span className={cx("num text-heading font-semibold", j.value > 0 ? (j.urgent ? "text-danger" : "text-ink") : "text-ink-muted")}>{j.value}</span>
            <ChevronRight className="size-4 shrink-0 text-ink-muted transition group-hover:translate-x-0.5 group-hover:text-ink" aria-hidden />
          </Link>
        </li>
      ))}
    </ol>
  );
}

/** Sales in the current calendar month (from the sales list). */
export function thisMonth<T extends { sale_date: string }>(rows: T[] | null | undefined): T[] {
  const ym = new Date().toISOString().slice(0, 7);
  return (rows ?? []).filter((s) => s.sale_date.startsWith(ym));
}
