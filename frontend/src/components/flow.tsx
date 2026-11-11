"use client";

/**
 * Stock-movement visual language: where stock is, where it is going, and how far a movement has got.
 * Used wherever it helps people read inventory flow (transfers, replenishment, dashboard).
 */

import { ArrowRight, Check, ChevronRight, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { fmtDateTime } from "@/lib/format";
import { cx, IconChip, type Tone } from "./ui";

export type StepState = "done" | "current" | "pending" | "failed";

export interface Step {
  label: string;
  state: StepState;
  at?: string | null;
  by?: string | null;
  note?: ReactNode;
}

function StepDot({ state }: { state: StepState }) {
  return (
    <span className={cx("relative z-10 inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2",
      state === "done" && "border-ink bg-ink text-white",
      state === "current" && "border-brand bg-brand-soft",
      state === "pending" && "border-line-strong bg-surface",
      state === "failed" && "border-danger bg-danger text-white")}>
      {state === "done" && <Check className="size-3.5" strokeWidth={3} aria-hidden />}
      {state === "failed" && <X className="size-3.5" strokeWidth={3} aria-hidden />}
      {state === "current" && <span className="size-2 rounded-full bg-brand-text" aria-hidden />}
    </span>
  );
}

const STATE_LABEL: Record<StepState, string> = { done: "completed", current: "in progress", pending: "not started", failed: "stopped" };

/** Progress through a document's lifecycle. Horizontal on wide screens, vertical on narrow ones. */
export function Timeline({ steps, className }: { steps: Step[]; className?: string }) {
  return (
    <ol className={cx("flex flex-col gap-0 md:flex-row", className)}>
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const lineDone = s.state === "done" && steps[i + 1] && steps[i + 1].state !== "pending";
        return (
          <li key={s.label} className="relative flex gap-3 pb-5 md:flex-1 md:flex-col md:gap-2 md:pb-0">
            {!last && (
              <span aria-hidden className={cx("absolute top-6 bottom-0 left-2.75 w-0.5 md:top-2.75 md:right-0 md:bottom-auto md:left-6 md:h-0.5 md:w-auto",
                lineDone ? "bg-ink" : "bg-line")} />
            )}
            <StepDot state={s.state} />
            <div className="min-w-0 md:pr-3">
              <div className={cx("text-label font-medium", s.state === "pending" ? "text-ink-muted" : s.state === "failed" ? "text-danger" : "text-ink")}>
                {s.label}<span className="sr-only"> — {STATE_LABEL[s.state]}</span>
              </div>
              {s.at && <div className="text-caption text-ink-muted">{fmtDateTime(s.at)}</div>}
              {s.by && <div className="text-caption text-ink-muted">{s.by}</div>}
              {s.note && <div className="mt-0.5 text-caption text-ink-secondary">{s.note}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Small dot-progress for table rows (e.g. transfer stage). */
export function MiniProgress({ total, done, failed, label }: { total: number; done: number; failed?: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={label} title={label}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={cx("h-1.5 w-4 rounded-full", failed && i === done ? "bg-danger" : i < done ? "bg-ink" : i === done ? "bg-brand" : "bg-line")} />
      ))}
    </span>
  );
}

export interface FlowNode {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  href?: string | null;
  icon?: LucideIcon;
  muted?: boolean;
}

function Node({ node, align }: { node: FlowNode; align: "left" | "right" }) {
  const title = node.href
    ? <Link href={node.href} className="link">{node.title}</Link>
    : <span className={node.muted ? "text-ink-muted" : "font-medium text-ink"}>{node.title}</span>;
  return (
    <div className={cx("flex min-w-0 flex-1 items-center gap-3 rounded-control border border-line bg-subtle p-4", align === "right" && "md:flex-row-reverse md:text-right")}>
      {node.icon && <IconChip icon={node.icon} tone={node.muted ? "default" : "accent"} />}
      <div className="min-w-0">
        <div className="text-caption font-medium tracking-wide text-ink-muted uppercase">{node.eyebrow}</div>
        <div className="truncate text-body-lg">{title}</div>
        {node.subtitle && <div className="truncate text-caption text-ink-muted">{node.subtitle}</div>}
      </div>
    </div>
  );
}

/** FROM → TO card for a stock movement. */
export function FlowPath({ from, to, via, tone = "default" }: { from: FlowNode; to: FlowNode; via?: ReactNode; tone?: Tone }) {
  return (
    <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center md:gap-0">
      <Node node={from} align="left" />
      <div className="flex shrink-0 items-center justify-center md:min-w-48 md:flex-col md:px-3">
        <div className="hidden h-0.5 w-full bg-line md:block" aria-hidden />
        {/* Wraps when the text is long (a long SKU on a phone) instead of widening the page. */}
        <div className={cx("my-1 inline-flex max-w-full flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 rounded-card border px-2.5 py-1 text-center text-caption font-medium wrap-anywhere",
          tone === "danger" ? "border-danger-line bg-danger-soft text-danger" : tone === "accent" || tone === "info" ? "border-info-line bg-info-soft text-info" : "border-line bg-surface text-ink-secondary")}>
          <ArrowRight className="size-3.5 rotate-90 md:rotate-0" aria-hidden />
          {via}
        </div>
        <div className="hidden h-0.5 w-full bg-line md:block" aria-hidden />
      </div>
      <Node node={to} align="right" />
    </div>
  );
}

/** Inline "A → B" for table cells. */
export function FlowInline({ from, to }: { from: ReactNode; to: ReactNode }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 text-label">
      <span className="truncate text-ink-secondary">{from}</span>
      <ArrowRight className="size-3.5 shrink-0 text-brand-text" aria-label="to" />
      <span className="truncate font-medium text-ink">{to}</span>
    </span>
  );
}

export interface PipelineStage {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  href?: string;
  icon: LucideIcon;
  tone?: Tone;
}

/** Horizontal stock pipeline: Warehouse → In transit → Reseller stock → Sold, awaiting invoice. */
export function StockPipeline({ stages, aside }: { stages: PipelineStage[]; aside?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 xl:flex-row">
      <ol className="flex flex-1 flex-col gap-2 md:flex-row md:items-stretch md:gap-0">
        {stages.map((s, i) => {
          const inner = (
            <>
              <IconChip icon={s.icon} tone={s.tone ?? "default"} size="sm" />
              <div className="min-w-0">
                <div className="text-caption font-medium whitespace-nowrap text-ink-muted">{s.label}</div>
                <div className="num text-metric-compact font-semibold text-ink">{s.value}</div>
                {s.hint && <div className="text-caption text-ink-muted">{s.hint}</div>}
              </div>
            </>
          );
          return (
            <li key={s.label} className="flex min-w-0 flex-1 items-center md:flex-row">
              {s.href
                ? <Link href={s.href} className="flex min-w-0 flex-1 items-start gap-3 rounded-control p-3 transition hover:bg-subtle focus-visible:outline-2 focus-visible:outline-ink md:flex-col md:gap-2">{inner}</Link>
                : <div className="flex min-w-0 flex-1 items-start gap-3 p-3 md:flex-col md:gap-2">{inner}</div>}
              {i < stages.length - 1 && <ChevronRight className="hidden size-4 shrink-0 text-line-strong md:block" aria-hidden />}
            </li>
          );
        })}
      </ol>
      {aside}
    </div>
  );
}
