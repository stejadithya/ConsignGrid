export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function fmtMoney(value?: string | number | null, currency?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  const s = n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency} ${s}` : s;
}

export function fmtQty(n?: number | null): string {
  return n === null || n === undefined ? "—" : n.toLocaleString();
}

export function todayIso(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

export function humanize(value?: string | null): string {
  if (!value) return "—";
  // Internal codes keep the word RESELLER; people see "dealer" (e.g. RESELLER_REPORT → "Dealer report").
  return value.toLowerCase().replace(/_/g, " ").replace(/\breseller(s?)\b/g, "dealer$1").replace(/^\w/, (c) => c.toUpperCase());
}
