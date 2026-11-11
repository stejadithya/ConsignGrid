"use client";

import { Download, FileSpreadsheet, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { Reseller } from "@/lib/types";
import { ProductSelect, shopText } from "./pickers";
import { Alert, Badge, Button, DataTable, Field, Input, Modal, ProductCell, Select, Tabs, Textarea } from "./ui";
import { branding } from "@/config/branding";

export interface StockLine { product: number | ""; qty: string }

export const blankLines = (): StockLine[] => [{ product: "", qty: "" }];

export function validLines(lines: StockLine[]) {
  return lines.filter((l) => l.product !== "" && Number(l.qty) > 0).map((l) => ({ product_id: Number(l.product), quantity: Number(l.qty) }));
}

/** Rows of tyre + quantity for the stock an existing reseller already holds. */
export function StockLinesEditor({ lines, onChange }: { lines: StockLine[]; onChange: (lines: StockLine[]) => void }) {
  const set = (i: number, patch: Partial<StockLine>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const units = validLines(lines).reduce((a, l) => a + l.quantity, 0);
  return (
    <div className="space-y-2">
      {lines.map((l, i) => (
        <div key={i} className="grid grid-cols-[1fr_6rem_auto] items-center gap-2">
          <ProductSelect value={l.product} onChange={(v) => set(i, { product: v })} />
          <Input type="number" min={1} aria-label={`Quantity held, line ${i + 1}`} placeholder="Qty" value={l.qty} onChange={(e) => set(i, { qty: e.target.value })} />
          <Button variant="ghost" aria-label={`Remove line ${i + 1}`} disabled={lines.length === 1} onClick={() => onChange(lines.filter((_, j) => j !== i))}><Trash2 aria-hidden /></Button>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button size="sm" onClick={() => onChange([...lines, { product: "", qty: "" }])}><Plus aria-hidden />Add tyre</Button>
        <span className="text-label text-ink-secondary"><b className="num text-ink">{units}</b> tyre(s)</span>
      </div>
    </div>
  );
}

export function postInitialStock(resellerId: number, locationId: number, lines: StockLine[], notes?: string) {
  return api.post(`/resellers/${resellerId}/initial-stock`, { location_id: locationId, lines: validLines(lines), notes: notes || null });
}

export const INITIAL_STOCK_TEMPLATE_URL = "/api/resellers/initial-stock/template";

export interface InitialStockCheck {
  rows: { row: number; sku: string; tyre: string | null; quantity: number; shop_code: string | null; errors: string[] }[];
  summary: { total: number; valid: number; errors: number; units: number };
  posted: { location_id: number; transaction_number: string; units: number }[] | null;
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The file could not be read"));
    reader.readAsDataURL(file);
  });
}

export async function importInitialStock(resellerId: number, file: File, commit: boolean) {
  return api.post<InitialStockCheck>(`/resellers/${resellerId}/initial-stock/import`,
    { filename: file.name, content_base64: await fileToBase64(file), commit });
}

/** Choose an Excel file (SKU Code, Quantity, Shop code). */
export function InitialStockFilePicker({ file, onChange }: { file: File | null; onChange: (f: File | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-wrap items-center gap-3 text-label">
      <a href={INITIAL_STOCK_TEMPLATE_URL} download className="inline-flex items-center gap-1.5 font-medium text-ink underline decoration-brand decoration-2 underline-offset-4">
        <Download className="size-4" aria-hidden />Download the template</a>
      <input ref={input} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only"
        aria-label="Initial stock Excel file" onChange={(e) => onChange(e.target.files?.[0] ?? null)} />
      <Button size="sm" onClick={() => input.current?.click()}><Upload aria-hidden />{file ? "Choose another file" : "Choose .xlsx file"}</Button>
      {file && <span className="flex items-center gap-1.5 truncate text-caption text-ink-secondary"><FileSpreadsheet className="size-3.5" aria-hidden />{file.name}</span>}
    </div>
  );
}

/** The checked rows of an initial-stock file. */
export function InitialStockPreview({ check }: { check: InitialStockCheck }) {
  const s = check.summary;
  return (
    <div className="space-y-2">
      <div className="text-label"><b className="num">{s.valid}</b> row(s) ready · <b className="num">{s.units}</b> tyre(s)
        {s.errors > 0 && <> · <span className="font-medium text-danger">{s.errors} row(s) with errors — fix them and choose the file again</span></>}</div>
      <DataTable label="Rows to import" search={false} rows={check.rows} rowKey={(r) => r.row} pageSize={20}
        columns={[
          { key: "r", header: "Row", cell: (r) => r.row },
          { key: "t", header: "Tyre", className: "min-w-48 whitespace-normal", cell: (r) => <ProductCell name={r.tyre ?? "—"} sku={r.sku} /> },
          { key: "q", header: "Qty", align: "right", cell: (r) => r.quantity || "—" },
          { key: "s", header: "Shop", cell: (r) => <span className="sku text-label">{r.shop_code ?? "—"}</span> },
          { key: "e", header: "Check", className: "min-w-48 whitespace-normal", cell: (r) => r.errors.length
            ? <span className="text-caption text-danger">{r.errors.join("; ")}</span> : <Badge value="ACTIVE" label="OK" /> },
        ]} />
    </div>
  );
}

/** Record the stock an existing reseller holds today: their "Initial stock (backorder)". */
export function InitialStockModal({ reseller, onClose, onDone }: { reseller: Reseller; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState("enter");
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<InitialStockCheck | null>(null);
  const locations = reseller.locations.filter((l) => l.is_active);
  const [location, setLocation] = useState<number | "">(locations.length === 1 ? locations[0].id : "");
  const [lines, setLines] = useState<StockLine[]>(blankLines);
  const [notes, setNotes] = useState("");
  const action = useAction();
  const ready = location !== "" && validLines(lines).length > 0;
  const excelFooter = !check
    ? <Button variant="primary" disabled={!file || action.busy} onClick={async () => { const c = await action.run(() => importInitialStock(reseller.id, file!, false)); if (c) setCheck(c); }}>{action.busy ? "Checking…" : "Check file"}</Button>
    : <Button variant="primary" disabled={!!check.summary.errors || !check.summary.valid || action.busy}
        onClick={async () => { if (await action.run(() => importInitialStock(reseller.id, file!, true))) onDone(); }}>{action.busy ? "Importing…" : `Import ${check.summary.units} tyre(s)`}</Button>;
  return (
    <Modal open wide title="Initial stock (backorder)" onClose={onClose}
      description={`Tyres ${reseller.business_name} already holds from ${branding.companyName}, recorded once when they join the system. They become this dealer's consignment stock.`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        {mode === "excel" ? excelFooter : <Button variant="primary" disabled={!ready || action.busy}
          onClick={async () => { if (await action.run(() => postInitialStock(reseller.id, Number(location), lines, notes))) onDone(); }}>
          {action.busy ? "Saving…" : "Add initial stock"}</Button>}</>}>
      <Tabs active={mode} onChange={(m) => { setMode(m); action.setError(null); }} tabs={[{ id: "enter", label: "Enter tyres" }, { id: "excel", label: "Upload Excel" }]} />
      <Alert>{action.error}</Alert>
      {mode === "excel" ? <>
        <InitialStockFilePicker file={file} onChange={(f) => { setFile(f); setCheck(null); action.setError(null); }} />
        <p className="text-caption text-ink-muted">Checking changes nothing. Shop code is optional when the dealer has one shop. Each shop gets one opening balance.</p>
        {check && <InitialStockPreview check={check} />}
      </> : <>
      {locations.length !== 1 && (
        <Field label="Location" required>{(id) => <Select id={id} value={location} onChange={(e) => setLocation(e.target.value ? Number(e.target.value) : "")}
          placeholder="Select location…" options={locations.map((l) => ({ value: l.id, label: `${shopText(l, false)} · ${l.code}` }))} />}</Field>
      )}
      <StockLinesEditor lines={lines} onChange={setLines} />
      <Field label="Notes">{(id) => <Textarea id={id} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Counted with the owner on 10 Oct" />}</Field>
      </>}
    </Modal>
  );
}
