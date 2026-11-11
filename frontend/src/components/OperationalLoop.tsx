import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, RefreshCw, ShoppingCart, Store, Warehouse, type LucideIcon } from "lucide-react";
import { branding } from "@/config/branding";
import { cx } from "./ui";
import { vocab } from "@/lib/terms";

interface Step { icon: LucideIcon; label: string; caption: string; place: string; highlight?: boolean }

// Read clockwise: top-left → top-right → bottom-right → bottom-left, then back up to the start.
const STEPS: Step[] = [
  { icon: Warehouse, label: "Warehouse", caption: "Stock received", place: "col-start-1 row-start-1" },
  { icon: Store, get label() { return vocab.Partner; }, caption: "On consignment", place: "col-start-3 row-start-1" },
  { icon: ShoppingCart, label: "Sale", caption: "Sold to a customer", place: "col-start-3 row-start-3" },
  { icon: RefreshCw, label: "Replenishment", caption: "Raised automatically", place: "col-start-1 row-start-3", highlight: true },
];

const ARROWS: { icon: LucideIcon; place: string; label?: string }[] = [
  { icon: ArrowRight, place: "col-start-2 row-start-1" },
  { icon: ArrowDown, place: "col-start-3 row-start-2" },
  { icon: ArrowLeft, place: "col-start-2 row-start-3" },
  // The return that closes the loop is named, so it reads as a cycle, not a sequence.
  { icon: ArrowUp, place: "col-start-1 row-start-2", label: "Back to the warehouse" },
];

/**
 * The operational loop, Warehouse → Dealer → Sale → Replenishment → Warehouse, as a closed 2 × 2 cycle. Charcoal on
 * white; yellow marks only Replenishment, the step the product automates. Screen readers get an ordered list that ends
 * back at the warehouse; the arrows are decoration.
 */
export function OperationalLoop({ className }: { className?: string }) {
  return (
    <div className={cx("relative grid grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)] grid-rows-[auto_2rem_auto] sm:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)]", className)}>
      <ol aria-label={`How ${branding.productName} keeps stock moving`} className="contents">
        {STEPS.map((s, i) => (
          <li key={s.label} className={cx("flex flex-col gap-2 rounded-card border border-line bg-surface p-3 shadow-card sm:flex-row sm:items-center sm:gap-3 sm:p-4", s.place)}>
            <span className={cx("inline-flex size-9 shrink-0 items-center justify-center rounded-control", s.highlight ? "bg-brand text-ink" : "bg-subtle text-ink")}>
              <s.icon className="size-4.5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-label font-medium text-ink">{s.label}</span>
              <span className="block text-caption text-ink-secondary">{s.caption}</span>
              <span className="sr-only">
                {s.highlight ? ` (automated by ${branding.productName})` : ""}{i === STEPS.length - 1 ? ", then back to the warehouse" : ""}
              </span>
            </span>
          </li>
        ))}
      </ol>
      {ARROWS.map((a) => (
        <span key={a.place} aria-hidden className={cx("flex items-center justify-center gap-1.5 text-ink", a.place)}>
          <a.icon className="size-5 shrink-0" strokeWidth={2.25} />
          {a.label && <span className="text-caption font-medium whitespace-nowrap">{a.label}</span>}
        </span>
      ))}
      {/* The centre says "this keeps going round". */}
      <span aria-hidden className="col-start-2 row-start-2 flex items-center justify-center text-ink-secondary">
        <RefreshCw className="size-4" />
      </span>
    </div>
  );
}
