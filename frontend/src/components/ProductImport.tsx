"use client";

import { CircleCheck, Download, FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { invalidateReference } from "@/components/pickers";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { Alert, Badge, Button, DataTable, Modal, QuickFilters } from "./ui";

interface ImportRow {
  row: number; sku: string; description: string; action: "create" | "update" | "unchanged" | "error";
  errors: string[]; warnings: string[]; changes: string[]; brand: string | null; pattern: string | null;
  size: string | null; load_index: string | null; speed_rating: string | null;
}
interface ImportResponse {
  filename: string | null; committed: boolean; sheet: string; header_row: number; columns: string[];
  summary: { create: number; update: number; unchanged: number; error: number; total: number };
  notes?: string[];
  result: { created: number; updated: number; unchanged: number; skipped: number } | null;
  rows: ImportRow[];
}

const ACTION_BADGE: Record<ImportRow["action"], { label: string; tone: "success" | "info" | "neutral" | "critical" }> = {
  create: { label: "New", tone: "success" }, update: { label: "Update", tone: "info" },
  unchanged: { label: "No change", tone: "neutral" }, error: { label: "Error", tone: "critical" },
};

/** All SKUs in the template layout (finding 15): edit or add rows, then use Import from Excel. */
export const EXPORT_URL = "/api/products/export";
export const TEMPLATE_URL = "/api/products/import/template";

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Import SKUs from Excel: check first (nothing changes), review every row, then import the valid rows. */
export function ProductImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<ImportResponse | null>(null);
  const [done, setDone] = useState<ImportResponse | null>(null);
  const [view, setView] = useState<"all" | "create" | "update" | "error">("all");
  const action = useAction();

  async function send(commit: boolean) {
    if (!file) return;
    const content_base64 = await toBase64(file);
    const res = await action.run(() => api.post<ImportResponse>("/products/import", { filename: file.name, content_base64, commit }));
    if (!res) return;
    if (commit) { setDone(res); invalidateReference(); onImported(); } else { setCheck(res); setView(res.summary.error ? "error" : "all"); }
  }

  const s = check?.summary;
  const importable = s ? s.create + s.update : 0;
  const rows = check ? check.rows.filter((r) => view === "all" || r.action === view) : null;

  return (
    <Modal open wide title="Import products from Excel" onClose={onClose}
      description="Creates new SKUs and updates the details of existing ones. Importing products never creates stock."
      footer={done ? <Button variant="primary" onClick={onClose}>Done</Button> : <>
        <Button onClick={onClose}>Cancel</Button>
        {!check
          ? <Button variant="primary" disabled={!file || action.busy} onClick={() => send(false)}>{action.busy ? "Checking…" : "Check file"}</Button>
          : <Button variant="primary" disabled={!importable || action.busy} onClick={() => send(true)}>
              {action.busy ? "Importing…" : `Import ${importable} product${importable === 1 ? "" : "s"}`}
            </Button>}
      </>}>
      <Alert>{action.error}</Alert>
      {done?.result ? (
        <Alert tone="success" title="Import complete">
          {done.result.created} new and {done.result.updated} updated product(s){done.result.skipped ? `; ${done.result.skipped} row(s) with errors were skipped` : ""}.
          Stock is unchanged — receive goods or post opening balances to add stock.
        </Alert>
      ) : (
        <>
          <ol className="grid gap-3 text-label sm:grid-cols-3">
            <li className="rounded-control border border-line bg-subtle p-3">
              <div className="font-medium">1. Use the standard template</div>
              <a href={TEMPLATE_URL} download className="mt-2 inline-flex items-center gap-1.5 font-medium text-ink underline decoration-brand decoration-2 underline-offset-4">
                <Download className="size-4" aria-hidden />Download blank template
              </a>
            </li>
            <li className="rounded-control border border-line bg-subtle p-3">
              <div className="font-medium">2. Choose the filled file</div>
              <input ref={input} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" aria-label="Excel file"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setCheck(null); action.setError(null); }} />
              <Button size="sm" className="mt-2" onClick={() => input.current?.click()}><Upload aria-hidden />{file ? "Choose another file" : "Choose .xlsx file"}</Button>
              {file && <div className="mt-1.5 flex items-center gap-1.5 truncate text-caption text-ink-secondary"><FileSpreadsheet className="size-3.5 shrink-0" aria-hidden />{file.name}</div>}
            </li>
            <li className="rounded-control border border-line bg-subtle p-3">
              <div className="font-medium">3. Check, then import</div>
              <p className="mt-1 text-caption text-ink-muted">Checking changes nothing. You see every row before importing; rows with errors are skipped.</p>
            </li>
          </ol>

          {check && s && (
            <>
              {check.notes?.map((n) => <Alert key={n} tone="info">{n}.</Alert>)}
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-control border border-line px-4 py-3 text-label">
                <span className="inline-flex items-center gap-1.5 font-medium"><CircleCheck className="size-4 text-success" aria-hidden />Checked {s.total} row(s)</span>
                <span><b className="num">{s.create}</b> new</span>
                <span><b className="num">{s.update}</b> to update</span>
                <span><b className="num">{s.unchanged}</b> unchanged</span>
                <span className={s.error ? "font-medium text-danger" : ""}><b className="num">{s.error}</b> with errors</span>
                <span className="ml-auto text-caption text-ink-muted">Sheet “{check.sheet}”, header row {check.header_row}</span>
              </div>
              <QuickFilters value={view} onChange={setView} options={[
                { id: "all", label: "All rows", count: s.total }, { id: "create", label: "New", count: s.create },
                { id: "update", label: "Updates", count: s.update }, { id: "error", label: "Errors", count: s.error },
              ]} />
              <div className="max-h-[45vh] overflow-auto rounded-control border border-line">
                <DataTable label="Import check" search={false} rows={rows} rowKey={(r) => r.row} pageSize={500} empty="No rows in this view"
                  rowClassName={(r) => r.action === "error" && "bg-danger-soft/40"}
                  columns={[
                    { key: "r", header: "Row", align: "right", cell: (r) => <span className="text-ink-muted">{r.row}</span> },
                    { key: "a", header: "Result", cell: (r) => <Badge value={r.action} label={ACTION_BADGE[r.action].label} tone={ACTION_BADGE[r.action].tone} /> },
                    { key: "s", header: "SKU", cell: (r) => <span className="sku text-label">{r.sku || "—"}</span> },
                    { key: "p", header: "Product & notes", className: "min-w-72 whitespace-normal", cell: (r) => (
                      <div>
                        {r.size
                          ? <div><span className="font-medium">{r.brand} {r.pattern}</span> <span className="text-caption text-ink-muted">{r.size} {r.load_index}{r.speed_rating}</span></div>
                          : <div className="text-ink-secondary">{r.description || "—"}</div>}
                        <div className="mt-0.5 space-y-0.5 text-caption">
                          {r.errors.map((e) => <div key={e} className="text-danger">{e}</div>)}
                          {r.changes.map((c) => <div key={c} className="text-ink-secondary">{c}</div>)}
                          {r.warnings.map((w) => <div key={w} className="text-warning">{w}</div>)}
                        </div>
                      </div>
                    ) },
                  ]} />
              </div>
            </>
          )}
        </>
      )}
    </Modal>
  );
}
