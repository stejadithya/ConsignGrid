"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Card, DataTable, Field, Input, Loading, MetricStrip, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { branding } from "@/config/branding";

interface Archive {
  value: number | null; unit: "days" | "months"; delete_after_archive_days: number;
  active: number; active_kb: number; archived: number; archived_kb: number; deleted: number;
  next_archive_on: string | null; next_delete_on: string | null;
}
interface ArchivedPhoto {
  id: number; entity_type: "delivery" | "transfer"; entity_id: number; number: string | null; size_kb: number;
  taken_at: string; archived_at: string; delete_on: string;
}

/** App settings for Relationship Managers and Administrators: drop-off photo archiving. */
export default function SettingsPage() {
  const { can } = useAuth();
  if (!can("settings.manage")) return <Alert>Settings are for Relationship Managers and Administrators.</Alert>;
  return (
    <>
      <PageHeader eyebrow="System" title="Settings" subtitle={`Settings that apply to everyone using ${branding.productName}.`} />
      <PhotoArchiving />
    </>
  );
}

function PhotoArchiving() {
  const { data, error, setData } = useApi<Archive>("/proofs/archive-settings");
  const { data: archived, reload } = useApi<ArchivedPhoto[]>("/proofs/archived");
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  return (
    <>
      <ArchiveForm key={`${data.value}-${data.unit}`} data={data} onSaved={setData} onRan={(d) => { setData(d); reload(); }} />
      <Card padded={false} title="Archived photos" className="mt-4"
        subtitle={`Hidden from normal screens. You can still open them until they are deleted, ${data.delete_after_archive_days} days after archiving.`}>
        <DataTable label="Archived photos" search={false} rows={archived} rowKey={(p) => p.id} empty="No archived photos"
          emptyHint="Photos appear here once they pass the archiving period."
          columns={[
            { key: "img", header: "Photo", cell: (p) => (
              <a href={`/api/proofs/photos/${p.id}`} target="_blank" rel="noreferrer" title="Open photo">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/proofs/photos/${p.id}`} alt="Archived drop-off photo" loading="lazy" className="size-12 rounded-md border border-line object-cover" />
              </a>) },
            { key: "r", header: "Delivery / transfer", cell: (p) => p.entity_type === "transfer"
              ? <Link className="link" href={`/transfers/${p.entity_id}`}>{p.number}</Link>
              : <Link className="link" href="/replenishment?tab=deliveries">{p.number}</Link> },
            { key: "t", header: "Taken", cell: (p) => fmtDate(p.taken_at) },
            { key: "a", header: "Archived", cell: (p) => fmtDate(p.archived_at) },
            { key: "d", header: "Deleted on", cell: (p) => <b className="font-medium">{fmtDate(p.delete_on)}</b> },
            { key: "s", header: "Size", align: "right", cell: (p) => `${p.size_kb} KB` },
          ]} />
      </Card>
    </>
  );
}

function ArchiveForm({ data, onSaved, onRan }: { data: Archive; onSaved: (d: Archive) => void; onRan: (d: Archive) => void }) {
  const [never, setNever] = useState(data.value === null);
  const [value, setValue] = useState(String(data.value ?? 6));
  const [unit, setUnit] = useState<"days" | "months">(data.unit);
  const [ran, setRan] = useState<string | null>(null);
  const action = useAction();
  const n = Number(value);
  const invalid = !never && (!Number.isInteger(n) || n < 1 || n > (unit === "months" ? 120 : 3650));
  const changed = never ? data.value !== null : n !== data.value || unit !== data.unit;

  async function save() {
    const r = await action.run(() => api.put<Archive>("/proofs/archive-settings", { value: never ? null : n, unit }));
    if (r) onSaved(r);
  }
  async function runNow() {
    const r = await action.run(() => api.post<{ archived: number; deleted: number }>("/proofs/retention/run"));
    if (r) {
      setRan(`Archived ${r.archived} photo(s), deleted ${r.deleted}.`);
      const fresh = await api.get<Archive>("/proofs/archive-settings");
      onRan(fresh);
    }
  }

  return (
    <Card title="Drop-off photo archiving"
      subtitle={`Photos taken when stock is handed to a dealer are archived after this period, then deleted ${data.delete_after_archive_days} days later. Who received the stock and the notes are always kept.`}>
      <Alert>{action.error}</Alert>
      <MetricStrip className="mb-4" items={[
        { label: "Active photos", value: data.active, hint: `${data.active_kb.toLocaleString()} KB` },
        { label: "Archived", value: data.archived, tone: data.archived ? "warn" : "default", hint: `${data.archived_kb.toLocaleString()} KB` },
        { label: "Deleted", value: data.deleted, hint: "Image removed, record kept" },
        { label: "Next archiving", value: data.next_archive_on ? fmtDate(data.next_archive_on) : "—", hint: data.value ? `After ${data.value} ${data.unit}` : "Archiving is off" },
        { label: "Next deletion", value: data.next_delete_on ? fmtDate(data.next_delete_on) : "—", hint: `${data.delete_after_archive_days} days after archiving` },
      ]} />
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Archive photos after">{(id) => <Input id={id} className="w-28" type="number" min={1} value={value} disabled={never} onChange={(e) => setValue(e.target.value)} />}</Field>
        <Field label="Unit">{(id) => <Select id={id} value={unit} disabled={never} onChange={(e) => setUnit(e.target.value as "days" | "months")}
          options={[{ value: "months", label: "Months" }, { value: "days", label: "Days" }]} />}</Field>
        <label className="mb-2 flex items-center gap-2 text-body">
          <input type="checkbox" className="size-4 accent-ink" checked={never} onChange={(e) => setNever(e.target.checked)} />Never archive
        </label>
        <Button variant="primary" className="mb-0.5" disabled={action.busy || invalid || !changed} onClick={save}>Save</Button>
      </div>
      {invalid && <p className="mt-1 text-caption text-danger">Choose 1–120 months or 1–3650 days.</p>}
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4 text-label text-ink-secondary">
        <span>The clean-up runs automatically every night. You can also run it now.</span>
        <Button size="sm" disabled={action.busy} onClick={runNow}>Run clean-up now</Button>
        {ran && <span className="text-success">{ran}</span>}
      </div>
    </Card>
  );
}
