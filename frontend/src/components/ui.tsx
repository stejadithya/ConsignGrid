"use client";

import {
  ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown, ChevronUp, CircleAlert, CircleCheck, Inbox, Info, MoreHorizontal, Search, SlidersHorizontal,
  TriangleAlert, X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import {
  createContext, useContext, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore, type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent as ReactKeyboardEvent, type Ref, type RefObject,
  type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { humanize } from "@/lib/format";
import { matchesSearch } from "@/lib/search";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export type Tone = "default" | "warn" | "danger" | "ok" | "info" | "accent";

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

/** `mobileActions`: what the header shows instead of `actions` below 1024px (phones and tablets in portrait), usually a
 *  `MoreMenu` of the secondary actions; the primary action then sits in a `MobileActionBar` at the bottom.
 *  `status`: a short note before the actions at every size (for example who the next step is waiting for), rendered
 *  once so it is never hidden in a menu. */
export function PageHeader({ title, subtitle, actions, eyebrow, meta, mobileActions, status }: {
  title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode; meta?: ReactNode; mobileActions?: ReactNode;
  status?: ReactNode;
}) {
  const responsive = mobileActions !== undefined || !!status;
  return (
    // The title keeps at least 16rem beside the actions; when there are many actions they wrap instead of squeezing it.
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0 md:min-w-64 md:flex-1">
        {eyebrow && <p className="mb-1 text-label font-medium text-ink-secondary">{eyebrow}</p>}
        <h1 className="text-display-compact font-bold text-ink sm:text-display">{title}</h1>
        {subtitle && <p className="mt-2 max-w-3xl text-body leading-6 text-ink-secondary">{subtitle}</p>}
        {meta && <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-ink-secondary">{meta}</div>}
      </div>
      {!responsive && actions && <div className="no-print flex flex-wrap items-center gap-2 md:justify-end">{actions}</div>}
      {responsive && (
        <div className="no-print flex flex-wrap items-center gap-2 md:justify-end">
          {status}
          {actions && <div className={mobileActions !== undefined ? "max-lg:hidden lg:contents" : "contents"}>{actions}</div>}
          {mobileActions && <div className="contents lg:hidden">{mobileActions}</div>}
        </div>
      )}
    </div>
  );
}

export function Card({ title, subtitle, icon: Icon, actions, children, className, padded = true }: {
  title?: ReactNode; subtitle?: ReactNode; icon?: LucideIcon; actions?: ReactNode; children: ReactNode; className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx("min-w-0 rounded-card border border-line bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-card py-3">
          {title && (
            <div className="flex min-w-0 items-center gap-2.5">
              {Icon && <Icon className="size-4 shrink-0 text-ink-muted" aria-hidden />}
              <div className="min-w-0">
                <h2 className="text-subheading font-semibold text-ink">{title}</h2>
                {subtitle && <p className="text-caption text-ink-muted">{subtitle}</p>}
              </div>
            </div>
          )}
          {actions && <div className="no-print flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-card" : ""}>{children}</div>
    </section>
  );
}

/** Heading for a group of cards on a page (e.g. "Needs attention"). */
export function SectionHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 className="text-heading font-semibold text-ink">{title}</h2>
        {description && <p className="mt-0.5 text-label text-ink-secondary">{description}</p>}
      </div>
      {actions && <div className="no-print flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** "accent" is the brand highlight (yellow), never a status; the other tones carry operational meaning. */
const CHIP_TONES: Record<Tone, string> = {
  default: "bg-neutral-soft text-ink-secondary", accent: "bg-brand-soft text-brand-text", warn: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger", ok: "bg-success-soft text-success", info: "bg-info-soft text-info",
};

export function IconChip({ icon: Icon, tone = "default", size = "md" }: { icon: LucideIcon; tone?: Tone; size?: "sm" | "md" }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center justify-center rounded-control", CHIP_TONES[tone], size === "sm" ? "size-7" : "size-9")}>
      <Icon className={size === "sm" ? "size-3.5" : "size-4.5"} aria-hidden />
    </span>
  );
}

/** KPI value colour: only a status that needs attention colours the number; "accent" and "info" stay ink. */
export const KPI_VALUE_TONES: Record<Tone, string> = {
  default: "text-ink", accent: "text-ink", info: "text-ink", ok: "text-ink", warn: "text-warning", danger: "text-danger",
};
/** KPI typography, shared by every KPI surface: 13px/500 label (two lines reserved on narrow screens so values
 *  in a row line up when a label wraps), 24px value on mobile and 30px from sm, 12px context line. */
export const KPI_LABEL = "line-clamp-2 min-h-9 text-label font-medium text-ink-secondary sm:min-h-0";
export const KPI_VALUE = "num text-metric-compact font-semibold sm:text-metric";
export const KPI_HINT = "text-caption text-ink-muted";

/** KPI card: icon chip, label, large value and one line of context. */
export function Stat({ label, value, hint, href, tone = "default", icon }: {
  label: string; value: ReactNode; hint?: ReactNode; href?: string; tone?: Tone; icon?: LucideIcon;
}) {
  const body = (
    <div className={cx("group relative flex h-full flex-col rounded-card border border-line bg-surface p-card shadow-card transition",
      href && "hover:border-line-strong hover:shadow-raised")}>
      <div className="flex flex-col items-start gap-2 sm:min-h-10 sm:flex-row sm:items-center sm:gap-3">
        {icon && <IconChip icon={icon} tone={tone} />}
        <div className={cx(KPI_LABEL, "min-w-0 flex-1")}>{label}</div>
        {href && <ArrowUpRight className="hidden size-4 text-ink-muted opacity-0 transition group-hover:opacity-100 sm:block" aria-hidden />}
      </div>
      <div className={cx(KPI_VALUE, "mt-3", KPI_VALUE_TONES[tone])}>{value}</div>
      {hint && <div className={cx(KPI_HINT, "mt-1")}>{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block h-full rounded-card focus-visible:focus-ring">{body}</Link> : body;
}

export const KpiCard = Stat;

/** A compact row of related metrics inside one surface (avoids walls of identical cards). */
export function MetricStrip({ items, className }: {
  items: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone; icon?: LucideIcon; href?: string }[]; className?: string;
}) {
  const tones: Record<Tone, string> = {
    default: "text-ink", accent: "text-ink", ok: "text-success", warn: "text-warning", danger: "text-danger", info: "text-info",
  };
  // A strip holds several figures in one surface, so its values use the compact KPI size at every width.
  return (
    <div className={cx("mb-6 grid grid-cols-2 overflow-hidden rounded-card border border-line bg-surface shadow-card sm:grid-cols-3",
      items.length >= 5 ? "lg:grid-cols-5" : items.length === 4 ? "lg:grid-cols-4" : "", className)}>
      {items.map((m) => {
        const body = (
          <>
            <div className="flex items-center gap-1.5 text-label font-medium text-ink-secondary">
              {m.icon && <m.icon className="size-3.5 shrink-0" aria-hidden />}<span className="line-clamp-2">{m.label}</span>
              {m.tone === "accent" && <span className="ml-0.5 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />}
              {m.href && <ArrowUpRight className="ml-auto size-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" aria-hidden />}
            </div>
            <div className={cx("num mt-1 text-metric-compact font-semibold", tones[m.tone ?? "default"])}>{m.value}</div>
            {m.hint && <div className={cx(KPI_HINT, "mt-0.5")}>{m.hint}</div>}
          </>
        );
        const cls = "-mr-px -mb-px border-r border-b border-line p-card";
        return m.href
          ? <Link key={m.label} href={m.href} className={cx(cls, "group block transition hover:bg-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink")}>{body}</Link>
          : <div key={m.label} className={cls}>{body}</div>;
      })}
    </div>
  );
}

/** Underline tabs. The selected tab is bold on a pale yellow tint with a thick yellow underline; hovering tints a tab
 *  and pressing darkens it. When the tabs don't fit (phones, tablets) the row scrolls sideways: an arrow at the edge
 *  shows there are more, and the selected tab is scrolled into view. */
export function Tabs({ tabs, active, onChange }: {
  tabs: { id: string; label: ReactNode; count?: number }[]; active: string; onChange: (id: string) => void;
}) {
  const [ref, edges] = useScrollEdges();
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[aria-selected=true]")?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [active, ref]);
  return (
    <div className="no-print relative mb-5">
      <div ref={ref} className="scroll-thin flex gap-1 overflow-x-auto border-b border-line" role="tablist">
        {tabs.map((t) => {
          const on = active === t.id;
          return (
            <button key={t.id} role="tab" type="button" aria-selected={on} onClick={() => onChange(t.id)}
              className={cx("relative -mb-px inline-flex min-h-control-md items-center gap-2 whitespace-nowrap rounded-t-control border-b-[3px] px-3 py-2 text-body transition-colors pointer-coarse:min-h-control-lg",
                "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink",
                on ? "border-brand bg-brand-soft font-semibold text-ink"
                  : "border-transparent font-medium text-ink-secondary hover:border-line-strong hover:bg-neutral-soft hover:text-ink active:bg-line")}>
              {t.label}
              {t.count !== undefined && (
                <span className={cx("num rounded-pill px-1.5 text-caption", on ? "bg-ink text-white" : "bg-neutral-soft text-ink-secondary")}>{t.count}</span>
              )}
            </button>
          );
        })}
      </div>
      <ScrollCue edges={edges} on="canvas" />
    </div>
  );
}

/** Edge cues for a row that scrolls sideways: a fade and an arrow on each side that has more content. `on` is the
 *  background the row sits on. Decoration only (the scroll area itself is what keyboard and screen readers use). */
function ScrollCue({ edges, on = "surface", hideStart, arrowAt = "center" }: {
  edges: { overflow: boolean; atStart: boolean; atEnd: boolean }; on?: "surface" | "canvas" | "any"; hideStart?: boolean; arrowAt?: "center" | "top";
}) {
  if (!edges.overflow) return null;
  // "any": the row may sit on white or off-white, so only the arrow is drawn.
  const from = on === "canvas" ? "from-canvas via-canvas/85" : on === "surface" ? "from-surface via-surface/85" : "from-transparent";
  const arrow = cx("absolute flex size-6 items-center justify-center rounded-full bg-ink text-white shadow-card",
    arrowAt === "top" ? "top-2" : "top-1/2 -translate-y-1/2");
  return (
    <>
      {!edges.atEnd && (
        <div aria-hidden className={cx("pointer-events-none absolute inset-y-0 right-0 w-12 bg-linear-to-l to-transparent", from)}>
          <span className={cx(arrow, "right-1")}><ChevronRight className="size-4" strokeWidth={2.5} /></span>
        </div>
      )}
      {!edges.atStart && !hideStart && (
        <div aria-hidden className={cx("pointer-events-none absolute inset-y-0 left-0 w-12 bg-linear-to-r to-transparent", from)}>
          <span className={cx(arrow, "left-1")}><ChevronLeft className="size-4" strokeWidth={2.5} /></span>
        </div>
      )}
    </>
  );
}

export function DefinitionList({ items, columns = 2 }: { items: [ReactNode, ReactNode][]; columns?: 1 | 2 }) {
  return (
    <dl className={cx("grid grid-cols-1 gap-x-8 text-body", columns === 2 && "sm:grid-cols-2")}>
      {items.map(([k, v], i) => (
        <div key={i} className="flex gap-3 border-b border-line/70 py-2.5">
          <dt className={cx("shrink-0 text-ink-muted", columns === 2 ? "w-32" : "w-40")}>{k}</dt>
          <dd className="min-w-0 text-ink">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return (
    <span aria-hidden className={cx("inline-flex shrink-0 items-center justify-center rounded-full bg-brand font-semibold text-ink",
      size === "sm" ? "size-7 text-caption" : size === "lg" ? "size-11 text-subheading" : "size-8 text-caption")}>
      {initials || "?"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------

const ALERT_TONES = {
  error: { cls: "border-danger-line bg-danger-soft text-danger", icon: CircleAlert },
  info: { cls: "border-info-line bg-info-soft text-info", icon: Info },
  success: { cls: "border-success-line bg-success-soft text-success", icon: CircleCheck },
  warn: { cls: "border-warning-line bg-warning-soft text-warning", icon: TriangleAlert },
};

export function Alert({ tone = "error", children, title }: { tone?: keyof typeof ALERT_TONES; children: ReactNode; title?: ReactNode }) {
  if (!children) return null;
  const { cls, icon: Icon } = ALERT_TONES[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("mb-4 flex gap-2.5 rounded-control border px-3.5 py-2.5 text-body", cls)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 text-ink">{title && <div className="font-medium">{title}</div>}{children}</div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-shimmer rounded-md bg-line", className)} />;
}

export function Loading({ label = "Loading…", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3 py-4">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-7 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <div className="grid grid-cols-2 gap-3 pt-3 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-10" />)}
    </div>
  );
}

export function EmptyState({ title, description, action, icon: Icon = Inbox, compact }: {
  title: ReactNode; description?: ReactNode; action?: ReactNode; icon?: LucideIcon; compact?: boolean;
}) {
  return (
    <div className={cx("flex flex-col items-center justify-center px-6 text-center", compact ? "py-8" : "py-12")}>
      <span className="mb-3 inline-flex size-10 items-center justify-center rounded-full bg-neutral-soft text-ink-muted">
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="text-body font-medium text-ink">{title}</div>
      {description && <p className="mt-1 max-w-sm text-label text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Empty({ children, description }: { children: ReactNode; description?: ReactNode }) {
  return <EmptyState title={children} description={description} compact />;
}

type BadgeTone = "success" | "warning" | "critical" | "info" | "neutral" | "accent";

/** Status colours: green done / on target, amber needs attention, red critical, blue informational / in transit,
 *  grey waiting / draft / closed. Yellow is the brand accent and never a status: the old "accent" tone now shows
 *  as informational. */
const BADGE_TONES: Record<BadgeTone, string> = {
  success: "bg-success-soft text-success ring-success-line",
  warning: "bg-warning-soft text-warning ring-warning-line",
  critical: "bg-danger-soft text-danger ring-danger-line",
  info: "bg-info-soft text-info ring-info-line",
  neutral: "bg-neutral-soft text-neutral ring-neutral-line",
  accent: "bg-info-soft text-info ring-info-line",
};

/** Business status → visual tone. The label is always shown, so colour is never the only signal.
 *  Grey: informational or simply waiting in the normal flow. Amber: someone needs to notice or act. Red: critical
 *  or failed. Blue: active work in progress. Green: done, approved, on target. Yellow is never a status. */
const STATUS_TONES: Record<string, BadgeTone> = {
  // Waiting or informational: grey
  DRAFT: "neutral", SUBMITTED: "neutral", REQUESTED: "neutral", OPEN: "neutral", CLOSED: "neutral", CANCELLED: "neutral",
  CREDITED: "neutral", VOID: "neutral", NOT_CHARGEABLE: "neutral", SUPERSEDED: "neutral", RELEASED: "neutral",
  CONSUMED: "neutral", NORMAL: "neutral", LOW: "neutral", TARGET_SHORTFALL: "neutral", MANUAL: "neutral", LATEST_STOCK: "neutral",
  // Needs attention or action: amber
  ON_HOLD: "warning", OVERDUE: "warning", UNINVOICED: "warning", HIGH: "warning", BACKORDER: "warning",
  AWAITING_RESELLER: "warning", RECHECK_REQUESTED: "warning", DISPUTED: "warning",
  ACTION_REQUIRED: "warning",   // screen-level labels for work someone must do (not a backend status)
  // Critical or failed: red
  URGENT: "critical", REJECTED: "critical", REJECT: "critical", DISCREPANCY: "critical", RECEIVED_WITH_DISCREPANCY: "critical",
  // Work in progress: blue
  UNDER_REVIEW: "info", PARTIALLY_APPROVED: "info", ALLOCATED: "info", PARTIALLY_FULFILLED: "info", PARTIALLY_RECEIVED: "info",
  READY_FOR_SHIPMENT: "info", SHIPPED: "info", DISPATCHED: "info", IN_TRANSIT: "info", ISSUED: "info", DRAFTED: "info",
  SALE: "info", TRANSFER: "info", STOCK_REQUEST: "info",
  // Done, approved, on target: green
  ACTIVE: "success", APPROVED: "success", COMPLETED: "success", FULFILLED: "success", RECEIVED: "success", DELIVERED: "success",
  INVOICED: "success", PAID: "success",
};

export function Badge({ value, label, tone }: { value: string | null | undefined; label?: string; tone?: BadgeTone }) {
  if (!value) return <span className="text-ink-muted">—</span>;
  const t = tone ?? STATUS_TONES[value] ?? "neutral";
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2 py-0.5 text-caption font-medium ring-1 ring-inset",
      BADGE_TONES[t], value === "VOID" && "line-through", value === "LOW" && "text-ink-muted")}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label ?? humanize(value)}
    </span>
  );
}

export const StatusBadge = Badge;

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

type BtnVariant = "primary" | "accent" | "secondary" | "danger" | "ghost";
type BtnSize = "sm" | "md" | "lg";

/** Primary: charcoal, the main action of an area (one per area). Secondary: white with a border, everything else.
 *  Ghost: low emphasis. Danger: confirming a destructive action only. Accent (yellow) is a rare brand highlight,
 *  never the default call to action. */
const BTN_VARIANTS: Record<BtnVariant, string> = {
  // Hover is clearly visible and pressing darkens further, so a click visibly registers.
  primary: "border-ink bg-ink text-white hover:border-ink-hover hover:bg-ink-hover active:bg-black",
  accent: "border-brand bg-brand text-ink hover:border-brand-hover hover:bg-brand-hover active:bg-brand-hover",
  secondary: "border-line-strong bg-surface text-ink hover:border-ink-secondary hover:bg-neutral-soft active:bg-line",
  danger: "border-danger bg-danger text-white hover:border-danger-hover hover:bg-danger-hover active:bg-danger-hover",
  ghost: "border-transparent bg-transparent text-ink-secondary hover:bg-neutral-soft hover:text-ink active:bg-line",
};
/** 32 / 36 / 44px at 14px (16px when large). On touch screens a regular button is 44px with 16px text; a small one
 *  (row actions, "Show more") stays compact at 36px but answers taps across 44 × 44px (touch-target). */
const BTN_SIZES: Record<BtnSize, string> = {
  sm: "h-control-sm px-3 text-button gap-1.5 [&_svg]:size-3.5 relative touch-target pointer-coarse:h-control-md",
  md: "h-control-md px-3.5 text-button gap-2 [&_svg]:size-4 pointer-coarse:h-control-lg pointer-coarse:px-4 pointer-coarse:text-button-lg",
  lg: "h-control-lg px-5 text-button-lg gap-2 [&_svg]:size-4.5",
};
const BTN_BASE = "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-control border font-semibold transition-colors focus-visible:focus-ring disabled:cursor-not-allowed disabled:opacity-50";

/** The button look for elements that cannot be a <Button> (download links, file-picker labels). */
export function buttonClass(variant: BtnVariant = "secondary", size: BtnSize = "md") {
  return cx(BTN_BASE, BTN_SIZES[size], BTN_VARIANTS[variant]);
}

export function Button({ variant = "secondary", size = "md", className, type = "button", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: BtnSize; ref?: Ref<HTMLButtonElement> }) {
  return <button type={type} {...props} className={cx(BTN_BASE, BTN_SIZES[size], BTN_VARIANTS[variant], className)} />;
}

export function ButtonLink({ href, children, variant = "secondary", size = "md", className }: {
  href: string; children: ReactNode; variant?: BtnVariant; size?: BtnSize; className?: string;
}) {
  return <Link href={href} className={cx(BTN_BASE, BTN_SIZES[size], BTN_VARIANTS[variant], className)}>{children}</Link>;
}

/** Inputs, selects and textareas: control border (3.4:1), charcoal focus ring, red when invalid. Text is 16px on
 *  phones and touch screens (iPhone Safari zooms into anything smaller) and 14px elsewhere; 44px tall on touch. */
const inputCls = "block w-full rounded-control border border-control bg-surface px-3 text-body-lg text-ink transition sm:text-body pointer-coarse:text-body-lg placeholder:text-ink-muted hover:border-ink-secondary focus:border-ink focus:outline-2 focus:outline-offset-1 focus:outline-ink disabled:cursor-not-allowed disabled:border-line-strong disabled:bg-subtle disabled:text-ink-disabled aria-[invalid=true]:border-danger aria-[invalid=true]:focus:outline-danger";
const CONTROL_H = "h-control-md pointer-coarse:h-control-lg";

/** A small ⓘ that explains a field. Opens on hover, keyboard focus or click; Esc closes it. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const id = useId();
  const shown = open || pinned;
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-label={`About ${label}`} aria-expanded={shown} aria-describedby={shown ? id : undefined}
        onClick={() => setPinned((p) => !p)} onFocus={() => setOpen(true)} onBlur={() => { setOpen(false); setPinned(false); }}
        onKeyDown={(e) => { if (e.key === "Escape") { setOpen(false); setPinned(false); } }}
        className="relative touch-target inline-flex size-4 items-center justify-center rounded-full text-ink-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-ink">
        <Info className="size-3.5" aria-hidden />
      </button>
      {shown && (
        <span id={id} role="tooltip"
          className="absolute top-full left-1/2 z-50 mt-1.5 w-64 -translate-x-1/2 rounded-control border border-line bg-surface px-3 py-2 text-label font-normal text-ink-secondary shadow-pop">
          {children}
        </span>
      )}
    </span>
  );
}

/** A labelled form field. `children` gets the control's id and, when there is an error or hint, the id of that message
 *  to put in the control's aria-describedby (so screen readers read it with the field). */
export function Field({ label, hint, error, children, required, info }: {
  label: string; hint?: ReactNode; error?: ReactNode; children: (id: string, describedBy?: string) => ReactNode; required?: boolean;
  /** Optional ⓘ explanation shown next to the label. */
  info?: ReactNode;
}) {
  const id = useId();
  const msgId = `${id}-msg`;
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1">
        <label htmlFor={id} className="block text-label font-medium text-ink">
          {label}{required && <span className="text-danger" aria-hidden> *</span>}
        </label>
        {info && <InfoTip label={label}>{info}</InfoTip>}
      </div>
      {children(id, error || hint ? msgId : undefined)}
      {error ? <p id={msgId} role="alert" className="mt-1.5 text-caption text-danger">{error}</p>
        : hint && <p id={msgId} className="mt-1.5 text-caption text-ink-muted">{hint}</p>}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputCls, CONTROL_H, props.className)} />;
}

export function SearchInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={cx("relative", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      <input type="search" {...props} className={cx(inputCls, CONTROL_H, "pl-9")} />
    </div>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={2} {...props} className={cx(inputCls, "py-2", props.className)} />;
}

// The chevron is an SVG data URL, which cannot read CSS variables: its fill is the ink-secondary token value (#68676f).
const CHEVRON = "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 20 20%22 fill=%22%2368676f%22><path d=%22M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z%22/></svg>')] bg-[length:16px] bg-[right_0.6rem_center] bg-no-repeat";

export function Select({ options, placeholder, ...props }: SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string | number; label: string; disabled?: boolean }[]; placeholder?: string;
}) {
  return (
    <select {...props} className={cx(inputCls, CHEVRON, CONTROL_H, "appearance-none pr-9", props.className)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>)}
    </select>
  );
}

/** Segmented quick filters (e.g. "Needs attention · Urgent · Awaiting stock"). */
export function QuickFilters<T extends string>({ options, value, onChange, label = "Quick filters" }: {
  options: { id: T; label: string; count?: number }[]; value: T; onChange: (id: T) => void; label?: string;
}) {
  const [ref, edges] = useScrollEdges();
  return (
    // Phones: one row that scrolls sideways inside itself (never the page), with an arrow while there is more. The
    // padding keeps focus rings visible inside the scroll box, and a focused chip scrolls into view.
    <div className="relative max-sm:min-w-0">
    <div ref={ref} role="group" aria-label={label}
      className="no-print flex flex-wrap gap-1.5 max-sm:-m-1 max-sm:w-[calc(100%+0.5rem)] max-sm:min-w-0 max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:p-1 max-sm:[scrollbar-width:none]">
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button key={o.id} type="button" aria-pressed={on} onClick={() => onChange(o.id)}
            onFocus={(e) => e.currentTarget.scrollIntoView({ block: "nearest", inline: "nearest" })}
            className={cx("inline-flex h-control-sm shrink-0 items-center gap-1.5 rounded-pill border px-3 text-label font-medium whitespace-nowrap transition-colors pointer-coarse:h-control-lg pointer-coarse:px-4",
              "focus-visible:focus-ring",
              on ? "border-ink bg-ink text-white" : "border-line-strong bg-surface text-ink-secondary hover:border-ink-secondary hover:bg-neutral-soft hover:text-ink active:bg-line")}>
            {o.label}
            {o.count !== undefined && (
              <span className={cx("num rounded-pill px-1.5 text-caption", on ? "bg-brand text-ink" : "bg-neutral-soft text-ink-secondary")}>{o.count}</span>
            )}
          </button>
        );
      })}
      </div>
      <ScrollCue edges={edges} on="any" />
    </div>
  );
}

/** Toolbar row for search + filters above a table or list. */
export function FilterBar({ children, end }: { children: ReactNode; end?: ReactNode }) {
  return (
    <div className="no-print flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
      {children}
      {end && <div className="ml-auto flex items-center gap-2">{end}</div>}
    </div>
  );
}

/** True inside the phone filter sheet. */
const FilterSheetContext = createContext(false);

/**
 * One table filter. In the toolbar it is just the control at its usual width; in the phone filter sheet it is full
 * width with its label shown above it. Give the control the same accessible name (aria-label) as `label`.
 */
export function FilterField({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  const inSheet = useContext(FilterSheetContext);
  if (!inSheet) return <div className={className}>{children}</div>;
  return (
    <div>
      <div aria-hidden className="mb-1.5 text-label font-medium text-ink">{label}</div>
      {children}
    </div>
  );
}

/** Whether a CSS media query matches (false during server rendering and hydration). */
function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window.matchMedia !== "function") return () => {};
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
    () => false,
  );
}

const FOCUSABLE = "a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

/** Bottom sheet for phones: a modal dialog docked at the bottom. Focus stays inside while it is open, Escape closes
 *  it, and focus goes back to the button that opened it. */
function BottomSheet({ title, onClose, returnFocus, children, footer }: {
  title: string; onClose: () => void; returnFocus: RefObject<HTMLElement | null>; children: ReactNode; footer: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const el = ref.current;
    el?.querySelector<HTMLElement>(FOCUSABLE)?.focus({ preventScroll: true });
    const back = returnFocus.current;
    return () => { back?.focus({ preventScroll: true }); };
  }, [returnFocus]);
  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
    if (e.key !== "Tab" || !ref.current) return;
    const els = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null);
    if (!els.length) return;
    const first = els[0], last = els[els.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  return toBody(
    <div className="fixed inset-0 z-50 flex flex-col justify-end bg-ink/40" onKeyDown={onKeyDown}>
      <div className="flex-1" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="flex max-h-[85vh] flex-col rounded-t-card border-t border-line bg-surface shadow-pop">
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
          <h2 id={titleId} className="text-subheading font-semibold text-ink">{title}</h2>
          <button type="button" onClick={onClose} className={CLOSE_BTN} aria-label="Close"><X className="size-4" aria-hidden /></button>
        </div>
        <div className="space-y-5 overflow-y-auto px-5 py-4">{children}</div>
        <div className="flex gap-2 border-t border-line bg-subtle px-5 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] [&>*]:flex-1">{footer}</div>
      </div>
    </div>,
  );
}

// ---------------------------------------------------------------------------
// Dialogs
// ---------------------------------------------------------------------------

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
}

const noopSubscribe = () => () => {};

/** True once rendered in the browser (false during server rendering and hydration). */
function useMounted() {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

/**
 * Dialogs render into document.body. Rendered in place, an ancestor with backdrop-filter (the blurred top bar)
 * becomes the containing block for position:fixed and traps the dialog inside it.
 */
function toBody(node: ReactNode) {
  return createPortal(node, document.body);
}

function useInitialFocus<T extends HTMLElement>(open: boolean) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open || !ref.current) return;
    const first = ref.current.querySelector<HTMLElement>("input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])");
    (first ?? ref.current).focus({ preventScroll: true });
  }, [open]);
  return ref;
}

/** Close (×) button of dialogs and drawers: 28px, with a 44 × 44px tap area on touch screens. */
const CLOSE_BTN = "relative touch-target -m-1 rounded-control p-1.5 text-ink-muted hover:bg-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-ink";

export function Modal({ open, title, description, onClose, children, footer, wide }: {
  open: boolean; title: ReactNode; description?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  useEscape(open, onClose);
  const mounted = useMounted();
  const ref = useInitialFocus<HTMLDivElement>(open && mounted);
  if (!open || !mounted) return null;
  return toBody(
    // A click outside never closes a pop-up (typed data would be lost); only its own Back / Cancel / × buttons do.
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-3 backdrop-blur-[2px] sm:p-10">
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
        className={cx("w-full rounded-card border border-line bg-surface shadow-pop outline-none", wide ? "max-w-3xl" : "max-w-lg")}
>
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-subheading font-semibold text-ink">{title}</h2>
            {description && <p className="mt-0.5 text-label text-ink-muted">{description}</p>}
          </div>
          <button type="button" onClick={onClose} className={CLOSE_BTN} aria-label="Close">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="space-y-4 px-5 py-5">{children}</div>
        {/* On phones the footer stays at the bottom of the screen while a long dialog scrolls (a dialog never gets the
            page's MobileActionBar). */}
        {footer && <div className="flex flex-wrap justify-end gap-2 rounded-b-card border-t border-line bg-subtle px-5 py-3 max-sm:sticky max-sm:bottom-0 max-sm:pb-[max(0.75rem,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>
  );
}

/** Side panel for reviewing a record without leaving the list. */
export function Drawer({ open, title, description, onClose, children, footer }: {
  open: boolean; title: ReactNode; description?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode;
}) {
  useEscape(open, onClose);
  const mounted = useMounted();
  const ref = useInitialFocus<HTMLDivElement>(open && mounted);
  if (!open || !mounted) return null;
  return toBody(
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/30 backdrop-blur-[1px]">
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
        className="flex h-full w-full max-w-2xl flex-col border-l border-line bg-surface shadow-pop outline-none"
>
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 className="text-subheading font-semibold text-ink">{title}</h2>
            {description && <p className="mt-0.5 text-label text-ink-muted">{description}</p>}
          </div>
          <button type="button" onClick={onClose} className={CLOSE_BTN} aria-label="Close">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-subtle px-6 py-3">{footer}</div>}
      </div>
    </div>
  );
}

interface ConfirmProps {
  open: boolean; title: string; message?: ReactNode; confirmLabel?: string; danger?: boolean; requireReason?: boolean;
  busy?: boolean; error?: string | null; onConfirm: (reason: string) => void; onClose: () => void; children?: ReactNode;
}

/** Confirmation dialog for high-impact actions; optionally requires a reason. */
export function ConfirmDialog(props: ConfirmProps) {
  return props.open ? <ConfirmBody {...props} /> : null;
}

function ConfirmBody({ title, message, confirmLabel = "Confirm", danger, requireReason, busy, error, onConfirm, onClose, children }: ConfirmProps) {
  const [reason, setReason] = useState("");
  return (
    <Modal open title={title} onClose={onClose} footer={<>
      <Button onClick={onClose}>Back</Button>
      <Button variant={danger ? "danger" : "primary"} disabled={busy || (requireReason && reason.trim().length < 3)}
        onClick={() => onConfirm(reason.trim())}>{busy ? "Working…" : confirmLabel}</Button>
    </>}>
      <Alert>{error}</Alert>
      {message && <div className="text-body leading-6 text-ink-secondary">{message}</div>}
      {children}
      {requireReason && (
        <Field label="Reason" required hint="Recorded in the audit trail.">
          {(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Data table
// ---------------------------------------------------------------------------

/** Card mode (phones): the part a column plays in the row's card. Identifier and status sit on the first line, then
 *  2–4 label/value fields, then the row's main action. Anything else stays on the detail page. */
export type MobileRole = "primary" | "secondary" | "status" | "field" | "action" | "hidden";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Value used for search and sorting. */
  value?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  className?: string;
  /** Numbers compared down the column: right-aligned with equal-width digits (the same as align: "right"). */
  numeric?: boolean;
  /** Card mode: this column's part in the card. Default: the first column is "primary", the others "hidden". */
  mobile?: MobileRole;
  /** Card mode: the label beside a "field" (default: the header, when it is text). */
  mobileLabel?: string;
  /** Card mode: order of "secondary" and "field" cells (lower first; default: column order). */
  mobileOrder?: number;
  /** Scrolling tables: keep this column in view while the rest scrolls sideways. Only the first column can be pinned. */
  pin?: boolean;
  /** Phones: offer this column under "Sort by" in the filter sheet (needs `value`). A string is the label to show
   *  there. Only columns people actually sort by, not every sortable one. */
  mobileSort?: boolean | string;
}

/** Where a sideways-scrolling box is: whether it overflows and whether it is at its start or end (for the edge fades). */
function useScrollEdges() {
  const ref = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ overflow: false, atStart: true, atEnd: true });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const overflow = el.scrollWidth > el.clientWidth + 1;
      const next = { overflow, atStart: el.scrollLeft <= 1, atEnd: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1 };
      setEdges((e) => (e.overflow === next.overflow && e.atStart === next.atStart && e.atEnd === next.atEnd ? e : next));
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    ro?.observe(el);
    if (el.firstElementChild) ro?.observe(el.firstElementChild);
    return () => { el.removeEventListener("scroll", update); ro?.disconnect(); };
  }, []);
  return [ref, edges] as const;
}

/** Card-mode classes per role (below 640px only; tablets and desktops keep the table). */
const CARD_CELL: Record<MobileRole, string> = {
  primary: "max-sm:col-start-1 max-sm:row-start-1 max-sm:self-center max-sm:font-medium",
  status: "max-sm:col-start-2 max-sm:row-start-1 max-sm:justify-self-end max-sm:self-start",
  secondary: "max-sm:col-span-2 max-sm:text-label max-sm:text-ink-secondary",
  field: "max-sm:col-span-2 max-sm:flex max-sm:items-baseline max-sm:justify-between max-sm:gap-4",
  action: "max-sm:col-span-2 max-sm:flex max-sm:justify-end max-sm:pt-1",
  hidden: "max-sm:hidden",
};
const CARD_ORDER: Record<MobileRole, number> = { primary: 0, status: 0, secondary: 1, field: 2, action: 9, hidden: 0 };

/** A table checkbox (row or "select all"): a compact box with a 44 × 44px tap area on touch screens; its label is
 *  for screen readers. */
export function TableCheckbox({ label, className, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: string }) {
  return (
    <label className={cx("relative touch-target inline-flex size-5 cursor-pointer items-center justify-center", className)}>
      <input type="checkbox" aria-label={label} {...props} className="size-4 cursor-pointer accent-ink" />
    </label>
  );
}

/** Tables: 14px body, 13px/600 headers, 44px rows (40px compact). Numbers right-aligned with equal-width digits.
 *
 *  Phones (below 640px): mobile="scroll" (default) keeps the table and scrolls it inside its card, with edge fades
 *  and an optional pinned first column; mobile="cards" shows each row as a card built from the columns' `mobile`
 *  roles. Cards are the same table restyled (explicit table roles, column headers kept for screen readers, card
 *  labels hidden from them), so there is one set of rows and nothing is announced twice.
 *
 *  density="comfortable": 52px rows and 16px numbers on touch screens (warehouse use); unchanged with a mouse. */
export function DataTable<T>({ rows, columns, rowKey, search = true, searchPlaceholder = "Search…", empty = "No records",
  emptyHint, emptyAction, filters, toolbar, pageSize = 50, footer, onRowClick, rowClassName, error, initialSearch = "", density = "default",
  mobile = "scroll", label, quickFilters, filterCount = 0, onClearFilters }: {
  rows: T[] | null | undefined; columns: Column<T>[]; rowKey: (row: T) => string | number; search?: boolean; initialSearch?: string;
  searchPlaceholder?: string; empty?: ReactNode; emptyHint?: ReactNode; emptyAction?: ReactNode; filters?: ReactNode;
  toolbar?: ReactNode; pageSize?: number; footer?: ReactNode; onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | false | undefined; error?: string | null; density?: "default" | "compact" | "comfortable";
  mobile?: "scroll" | "cards";
  /** Accessible name of the table (and of its scroll area). */
  label?: string;
  /** Quick-filter chips: always visible (one sideways-scrolling row on phones). */
  quickFilters?: ReactNode;
  /** Phones: `filters` move into a "Filters" sheet; this is how many differ from their default ("Filters (2)"). */
  filterCount?: number;
  /** Resets `filters` to their defaults (the sheet's "Clear all"). */
  onClearFilters?: () => void;
}) {
  const [q, setQ] = useState(initialSearch);
  const phone = useMediaQuery("(width < 40rem)");
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetButton = useRef<HTMLButtonElement>(null);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [limit, setLimit] = useState(pageSize);
  const [scrollRef, scroll] = useScrollEdges();
  const filtered = useMemo(() => {
    let out = rows ?? [];
    if (q.trim()) {
      // Every word typed must appear somewhere in the row; case, spaces and punctuation are ignored, so "195 65"
      // finds 195/65R15 (lib/search).
      out = out.filter((r) => matchesSearch(columns.map((c) => String(c.value?.(r) ?? "")), q));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.value) {
        out = [...out].sort((a, b) => {
          const va = col.value!(a) ?? "", vb = col.value!(b) ?? "";
          return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
        });
      }
    }
    return out;
  }, [rows, q, sort, columns]);
  const cards = mobile === "cards";
  const isNum = (c: Column<T>) => c.numeric || c.align === "right";
  const align = (c: Column<T>) => (isNum(c) ? "text-right" : c.align === "center" ? "text-center" : "text-left");
  const role = (c: Column<T>, i: number): MobileRole => c.mobile ?? (i === 0 ? "primary" : "hidden");
  const pinned = (c: Column<T>, i: number) => i === 0 && !!c.pin;
  const pinCls = (cell: "th" | "td") => cx("sticky left-0 z-[1]", cell === "th" ? "bg-subtle" : "bg-surface group-hover:bg-subtle",
    !scroll.atStart && "shadow-[inset_-1px_0_0_var(--color-line)]", cards && "max-sm:static max-sm:shadow-none");
  const rowH = density === "compact" ? "h-row-compact" : density === "comfortable" ? "h-row pointer-coarse:h-row-comfortable" : "h-row";
  const numTouch = density === "comfortable" ? "pointer-coarse:text-body-lg pointer-coarse:font-semibold" : "";
  const fieldLabel = (c: Column<T>) => c.mobileLabel ?? (typeof c.header === "string" ? c.header : "");
  const tableName = label;
  const sortable = columns.filter((c) => c.mobileSort && c.value);
  const sortName = (c: Column<T>) => (typeof c.mobileSort === "string" ? c.mobileSort : fieldLabel(c) || c.key);
  const sortedCol = sort && columns.find((c) => c.key === sort.key);
  const sortText = sortedCol ? `Sorted by ${sortable.includes(sortedCol) ? sortName(sortedCol) : fieldLabel(sortedCol) || sortedCol.key}, ${sort.dir === 1 ? "ascending" : "descending"}` : "";
  // Phones: secondary filters and sorting live in one sheet behind a "Filters" (or "Sort") button. The filters are
  // rendered in one place at a time (toolbar or sheet), so each control exists once.
  const sheetFilters = phone && !!filters;
  const hasSheet = phone && (!!filters || sortable.length > 0);
  const sheetTitle = filters ? (sortable.length ? "Filters and sort" : "Filters") : "Sort";

  return (
    <div>
      {(search || filters || toolbar) && (
        <div className="no-print flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          {search && (
            <SearchInput className="w-full sm:w-72" aria-label="Search table" placeholder={searchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} />
          )}
          {quickFilters && <div className="max-sm:w-full max-sm:min-w-0">{quickFilters}</div>}
          {!sheetFilters && filters && <div className="contents max-sm:hidden">{filters}</div>}
          {hasSheet && (
            <Button ref={sheetButton} aria-haspopup="dialog" onClick={() => setSheetOpen(true)}>
              <SlidersHorizontal aria-hidden />{filters ? "Filters" : "Sort"}{filters && filterCount > 0 && <span className="num"> ({filterCount})</span>}
            </Button>
          )}
          <div className="ml-auto flex items-center gap-3">
            {toolbar}
            {/* Announces sort changes; shown on phones, where the column headers are hidden. */}
            <span aria-live="polite" className="text-caption text-ink-secondary sm:sr-only">{sortText}</span>
            <span className="num text-caption text-ink-muted">{filtered.length} row{filtered.length === 1 ? "" : "s"}</span>
          </div>
        </div>
      )}
      {hasSheet && sheetOpen && (
        <BottomSheet title={sheetTitle} onClose={() => setSheetOpen(false)} returnFocus={sheetButton}
          footer={<>
            <Button disabled={filterCount === 0 && !sort} onClick={() => { onClearFilters?.(); setSort(null); }}>Clear all</Button>
            <Button variant="primary" onClick={() => setSheetOpen(false)}>Apply ({filtered.length} row{filtered.length === 1 ? "" : "s"})</Button>
          </>}>
          {filters && (
            <FilterSheetContext.Provider value>
              <div className="space-y-4 [&>*]:w-full">{filters}</div>
            </FilterSheetContext.Provider>
          )}
          {sortable.length > 0 && (
            <div className="space-y-4">
              <fieldset>
                <legend className="mb-1.5 text-label font-medium text-ink">Sort by</legend>
                <div className="divide-y divide-line rounded-control border border-line">
                  {[{ key: "", name: "Default order" }, ...sortable.map((c) => ({ key: c.key, name: sortName(c) }))].map((o) => (
                    <label key={o.key} className="flex min-h-11 cursor-pointer items-center gap-3 px-3 text-body-lg">
                      <input type="radio" name="table-sort-by" className="size-4.5 accent-ink" checked={(sort?.key ?? "") === o.key}
                        onChange={() => setSort(o.key ? { key: o.key, dir: sort?.dir ?? 1 } : null)} />{o.name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset disabled={!sort}>
                <legend className="mb-1.5 text-label font-medium text-ink">Order</legend>
                <div className="grid grid-cols-2 gap-2">
                  {([[1, "Ascending"], [-1, "Descending"]] as const).map(([dir, name]) => (
                    <label key={dir} className={cx("flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-control border px-3 text-body-lg",
                      sort?.dir === dir ? "border-ink bg-brand-soft font-medium" : "border-line-strong", !sort && "cursor-not-allowed opacity-50")}>
                      <input type="radio" name="table-sort-dir" className="size-4.5 accent-ink" checked={!!sort && sort.dir === dir}
                        onChange={() => sort && setSort({ key: sort.key, dir })} />{name}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          )}
        </BottomSheet>
      )}
      {error && <div className="px-4 pt-3"><Alert>{error}</Alert></div>}
      <div className="relative">
        {/* The scroll box is relative so absolutely positioned content (screen-reader labels) stays inside it; without
            that it sat past the last column and widened whole pages on phones. When it overflows it is focusable, so
            keyboard users can scroll it with the arrow keys. */}
        <div ref={scrollRef} className="scroll-thin relative overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink"
          {...(scroll.overflow ? { tabIndex: 0, role: "region", "aria-label": `${tableName ?? "Table"}, scrolls sideways` } : {})}>
          <table className={cx("min-w-full text-body", cards && "max-sm:block")} aria-label={tableName} {...(cards ? { role: "table" } : {})}>
            <thead className={cx(cards && "max-sm:sr-only")} {...(cards ? { role: "rowgroup" } : {})}>
              <tr className="border-b border-line bg-subtle" {...(cards ? { role: "row" } : {})}>
                {columns.map((c, i) => {
                  const sorted = sort?.key === c.key;
                  return (
                    <th key={c.key} scope="col" aria-sort={sorted ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                      {...(cards ? { role: "columnheader" } : {})}
                      className={cx("h-10 whitespace-nowrap px-4 text-label font-semibold text-ink-secondary pointer-coarse:h-control-lg", align(c),
                        pinned(c, i) && pinCls("th"))}>
                      {c.value ? (
                        <button type="button" onClick={() => setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 }))}
                          className={cx("group relative touch-target inline-flex items-center gap-1 rounded hover:text-ink focus-visible:outline-2 focus-visible:outline-ink", sorted && "text-ink",
                            isNum(c) && "flex-row-reverse")}>
                          {c.header}
                          {sorted ? (sort.dir === 1 ? <ChevronUp className="size-3.5" aria-hidden /> : <ChevronDown className="size-3.5" aria-hidden />)
                            : <ChevronsUpDown className="size-3.5 opacity-0 transition group-hover:opacity-60" aria-hidden />}
                        </button>
                      ) : c.header}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className={cx(cards && "max-sm:grid max-sm:gap-3 max-sm:bg-subtle max-sm:p-3")} {...(cards ? { role: "rowgroup" } : {})}>
              {rows === null || rows === undefined ? (
                Array.from({ length: 5 }, (_, i) => (
                  <tr key={i} className={cx("border-b border-line/70 last:border-0", cards && "max-sm:block max-sm:rounded-card max-sm:bg-surface max-sm:p-card")} {...(cards ? { role: "row" } : {})}>
                    {columns.map((c) => <td key={c.key} {...(cards ? { role: "cell" } : {})} className={cx(rowH, "px-4", cards && "max-sm:block max-sm:h-auto max-sm:p-0 max-sm:py-1")}>
                      <Skeleton className={cx("h-3.5", isNum(c) ? "ml-auto w-10" : "w-24")} /></td>)}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr className={cx(cards && "max-sm:block max-sm:rounded-card max-sm:bg-surface")} {...(cards ? { role: "row" } : {})}>
                  <td colSpan={columns.length} {...(cards ? { role: "cell" } : {})} className={cx(cards && "max-sm:block")}>
                    <EmptyState compact title={q ? "No matching records" : empty}
                      description={q ? `Nothing matches “${q}”. Try a different search.` : emptyHint} action={q ? undefined : emptyAction} />
                  </td>
                </tr>
              ) : (
                filtered.slice(0, limit).map((r) => (
                  <tr key={rowKey(r)} onClick={() => onRowClick?.(r)} {...(cards ? { role: "row" } : {})}
                    className={cx("group border-b border-line/70 transition-colors last:border-0 hover:bg-subtle", onRowClick && "cursor-pointer hover:bg-neutral-soft active:bg-line",
                      cards && "max-sm:grid max-sm:grid-cols-[minmax(0,1fr)_auto] max-sm:gap-x-3 max-sm:gap-y-1.5 max-sm:rounded-card max-sm:border max-sm:border-line max-sm:bg-surface max-sm:p-card max-sm:shadow-card",
                      rowClassName?.(r))}>
                    {columns.map((c, i) => {
                      const part = role(c, i);
                      return (
                        <td key={c.key} {...(cards ? { role: "cell" } : {})} {...(cards && part === "field" ? { "data-label": fieldLabel(c) } : {})}
                          style={cards && (part === "field" || part === "secondary" || part === "action") ? { order: part === "action" ? CARD_ORDER.action : c.mobileOrder ?? CARD_ORDER[part] } : undefined}
                          className={cx(rowH, "whitespace-nowrap px-4 py-2 align-middle", isNum(c) && cx("num", numTouch), align(c), c.className,
                            pinned(c, i) && pinCls("td"),
                            cards && cx("max-sm:h-auto max-sm:min-w-0 max-sm:p-0 max-sm:whitespace-normal max-sm:text-left", CARD_CELL[part], part === "field" && "card-label"))}>
                          {/* A field's card label comes from data-label (CSS), so the cell's own text is unchanged. */}
                          {cards && part === "field" ? <span className="max-sm:text-right sm:contents">{c.cell(r)}</span> : c.cell(r)}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
            {footer}
          </table>
        </div>
        {/* Edge cues: more columns to the left / right (a fade and an arrow by the header row). They follow the scroll
            position and disappear at the ends. */}
        <ScrollCue edges={scroll} hideStart={!!columns[0]?.pin} arrowAt="top" />
      </div>
      {filtered.length > limit && (
        <div className="no-print border-t border-line p-3 text-center">
          <Button size="sm" onClick={() => setLimit((l) => l + pageSize)}>Show more ({filtered.length - limit} remaining)</Button>
        </div>
      )}
    </div>
  );
}

export function Qty({ value, zeroMuted = true, tone }: { value: number | null | undefined; zeroMuted?: boolean; tone?: "warn" | "danger" | "ok" }) {
  if (value === null || value === undefined) return <span className="text-ink-muted">—</span>;
  const tones = { warn: "text-warning font-semibold", danger: "text-danger font-semibold", ok: "text-success" };
  return <span className={cx("num", value === 0 && zeroMuted ? "text-ink-muted" : tone ? tones[tone] : "")}>{value.toLocaleString()}</span>;
}

/** Product identity for tables: brand + pattern prominent, size and SKU beneath (13px, Inter, readable). */
export function ProductCell({ sku, name, size }: { sku?: string | null; name?: string | null; size?: string | null }) {
  return (
    <div className="max-w-[17rem] min-w-[10rem]" title={name ?? undefined}>
      <div className="truncate font-medium text-ink">{name ?? sku ?? "—"}</div>
      <div className="flex items-center gap-1.5 whitespace-nowrap text-label text-ink-secondary">
        {size && <span className="data font-semibold">{size}</span>}
        {size && sku && <span aria-hidden className="text-ink-muted">·</span>}
        {sku && <span className="sku">{sku}</span>}
      </div>
    </div>
  );
}

/** Compact "⋯" row menu for secondary actions. */
export function ActionMenu({ label, items }: { label: string; items: { label: string; onSelect: () => void; danger?: boolean }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  if (!items.length) return null;
  return (
    <div className="relative inline-block text-left" ref={ref} onClick={(e) => e.stopPropagation()}>
      <button type="button" aria-label={label} aria-haspopup="menu" aria-expanded={open} title={label} onClick={() => setOpen((o) => !o)}
        className="relative touch-target rounded-control p-1.5 text-ink-muted hover:bg-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-ink">
        <MoreHorizontal className="size-4" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-44 overflow-hidden rounded-control border border-line bg-surface p-1 shadow-pop">
          {items.map((it) => (
            <button key={it.label} type="button" role="menuitem" onClick={() => { setOpen(false); it.onSelect(); }}
              className={cx("block w-full rounded-md px-2.5 py-1.5 text-left text-body hover:bg-subtle pointer-coarse:py-3", it.danger ? "text-danger" : "text-ink")}>
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export interface MoreMenuItem {
  label: string;
  onSelect?: () => void;
  href?: string;
  /** With href: a file download (a plain link, not client navigation). */
  download?: boolean;
  icon?: LucideIcon;
  /** Destructive (Cancel, Reject, Void): red, listed last after a divider. The label must say what it does. */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * "More" menu for a page's secondary actions on phones and tablets in portrait. A labelled button (never icon-only),
 * 44px on touch screens. Opens with Enter, Space or ↓ and focuses the first item; ↑ ↓ Home End move; Escape closes
 * and returns focus to the button. Destructive items come last, after a divider. With one item it shows that item
 * as a plain button instead.
 */
export function MoreMenu({ items, label = "More actions" }: { items: (MoreMenuItem | false | null | undefined)[]; label?: string }) {
  const list = items.filter((i): i is MoreMenuItem => !!i);
  const ordered = [...list.filter((i) => !i.danger), ...list.filter((i) => i.danger)];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const close = (focusTrigger: boolean) => { setOpen(false); if (focusTrigger) trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    ref.current?.querySelector<HTMLElement>("[role=menuitem]:not([aria-disabled=true])")?.focus();
    const onDown = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);
  if (!ordered.length) return null;
  if (ordered.length === 1) {
    const [it] = ordered;
    const Icon = it.icon;
    return it.href && it.download
      ? <a href={it.href} download className={buttonClass()}>{Icon && <Icon className="size-4" aria-hidden />}{it.label}</a>
      : it.href
      ? <ButtonLink href={it.href}>{Icon && <Icon aria-hidden />}{it.label}</ButtonLink>
      : <Button variant={it.danger ? "danger" : "secondary"} disabled={it.disabled} onClick={it.onSelect}>{Icon && <Icon aria-hidden />}{it.label}</Button>;
  }
  const onMenuKey = (e: ReactKeyboardEvent) => {
    const els = [...(ref.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
    const at = els.indexOf(document.activeElement as HTMLElement);
    const go = (i: number) => { e.preventDefault(); els[(i + els.length) % els.length]?.focus(); };
    if (e.key === "ArrowDown") go(at + 1);
    else if (e.key === "ArrowUp") go(at - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(els.length - 1);
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key === "Tab") setOpen(false);
  };
  const itemCls = (danger?: boolean) => cx("flex min-h-9 w-full items-center gap-2 rounded-md px-3 text-left text-body pointer-coarse:min-h-11 pointer-coarse:text-body-lg",
    "hover:bg-neutral-soft focus-visible:bg-neutral-soft active:bg-line focus-visible:outline-2 focus-visible:outline-ink aria-disabled:cursor-not-allowed aria-disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
    danger ? "font-medium text-danger" : "text-ink");
  const firstDanger = ordered.findIndex((i) => i.danger);
  // Header actions sit on the left on phones and on the right from 768px, so the menu opens towards the screen.
  return (
    <div className="relative" ref={ref} onKeyDown={open ? onMenuKey : undefined}>
      <Button ref={trigger} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} aria-label={label}
        onClick={() => setOpen((o) => !o)} onKeyDown={(e) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); setOpen(true); } }}>
        <MoreHorizontal aria-hidden />More
      </Button>
      {open && (
        <div id={menuId} role="menu" aria-label={label}
          className="absolute left-0 z-40 mt-1 w-64 max-w-[calc(100vw-2rem)] rounded-control md:right-0 md:left-auto border border-line bg-surface p-1 shadow-pop">
          {ordered.map((it, i) => {
            const Icon = it.icon;
            const body = <>{Icon && <Icon aria-hidden />}{it.label}</>;
            return (
              <div key={it.label} className={cx(i === firstDanger && i > 0 && "mt-1 border-t border-line pt-1")}>
                {it.href && !it.disabled && it.download
                  ? <a href={it.href} download role="menuitem" tabIndex={-1} className={itemCls(it.danger)} onClick={() => setOpen(false)}>{body}</a>
                  : it.href && !it.disabled
                  ? <Link href={it.href} role="menuitem" tabIndex={-1} className={itemCls(it.danger)} onClick={() => setOpen(false)}>{body}</Link>
                  : <button type="button" role="menuitem" tabIndex={-1} aria-disabled={it.disabled || undefined} className={itemCls(it.danger)}
                      onClick={() => { if (it.disabled) return; close(true); it.onSelect?.(); }}>{body}</button>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Focus in one of these on a touch screen opens the on-screen keyboard. */
const TEXT_ENTRY = "input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]):not([type=reset]):not([type=range]):not([type=file]):not([type=color]), textarea, select, [contenteditable=true]";

/**
 * The page's one primary action (with Back, Cancel or Save draft beside it, if needed), docked to the bottom of the
 * screen on phones and tablets in portrait (below 1024px), above the iPhone home indicator. Wider screens show it in
 * place (`desktop="inline"`) or not at all when the page header already has it (`desktop="hidden"`).
 *
 * - Put it after the content it acts on, so the focus order is content → action.
 * - It publishes its height as --action-bar-height: the page gets that much bottom padding (the last field is never
 *   covered), focused fields scroll clear of it (scroll-padding), and phone notifications sit above it.
 * - While a text field is focused on a touch screen (the on-screen keyboard is open) it drops back into the page flow
 *   instead of floating over the field.
 * - Never inside a dialog: a dialog's footer holds its actions.
 */
export function MobileActionBar({ children, desktop = "inline", align = "end", label = "Page actions" }: {
  children: ReactNode; desktop?: "inline" | "hidden"; align?: "start" | "end"; label?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    const touch = () => typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
    const entry = (t: EventTarget | null) =>
      t instanceof Element && t.matches(TEXT_ENTRY) && !ref.current?.contains(t) && !t.closest("[role=dialog]");
    const onIn = (e: FocusEvent) => setTyping(touch() && entry(e.target));
    const onOut = (e: FocusEvent) => setTyping(touch() && entry(e.relatedTarget));
    document.addEventListener("focusin", onIn);
    document.addEventListener("focusout", onOut);
    return () => { document.removeEventListener("focusin", onIn); document.removeEventListener("focusout", onOut); };
  }, []);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement;
    const update = () => root.style.setProperty("--action-bar-height",
      getComputedStyle(el).position === "fixed" ? `${el.getBoundingClientRect().height}px` : "0px");
    update();
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    ro?.observe(el);
    const wide = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 64rem)") : null;
    wide?.addEventListener("change", update);
    return () => { ro?.disconnect(); wide?.removeEventListener("change", update); root.style.removeProperty("--action-bar-height"); };
  }, [typing]);
  return (
    <div ref={ref} role="group" aria-label={label} data-mobile-action-bar=""
      className={cx("no-print flex flex-wrap items-center justify-end gap-2",
        typing
          ? "max-lg:mt-4"
          : "max-lg:fixed max-lg:inset-x-0 max-lg:bottom-0 max-lg:z-40 max-lg:border-t max-lg:border-line max-lg:bg-surface max-lg:px-page max-lg:pt-3 max-lg:pb-[max(0.75rem,env(safe-area-inset-bottom))] max-lg:shadow-pop",
        "max-sm:[&>*]:flex-1", align === "start" && "lg:justify-start", desktop === "hidden" && "lg:hidden")}>
      {children}
    </div>
  );
}
