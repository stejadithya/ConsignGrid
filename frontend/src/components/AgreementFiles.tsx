"use client";

import { FileText, Trash2, Upload } from "lucide-react";
import { useRef } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { fileToBase64 } from "./InitialStock";
import { Alert, Button, Card, EmptyState } from "./ui";

interface AgreementFile { id: number; filename: string; content_type: string; size_bytes: number; uploaded_at: string; uploaded_by: string | null }

export const AGREEMENT_ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp";
export const AGREEMENT_MAX_BYTES = 5 * 1024 * 1024;

export async function uploadAgreement(resellerId: number, file: File) {
  if (file.size > AGREEMENT_MAX_BYTES) throw new Error("The file is larger than 5 MB.");
  return api.post(`/resellers/${resellerId}/agreement-files`, { filename: file.name, content_base64: await fileToBase64(file) });
}

/** Copies of the signed consignment agreement (D8): PDF or photo, up to 5 MB each. */
export function AgreementFilesCard({ resellerId, canEdit }: { resellerId: number; canEdit: boolean }) {
  const { data, reload } = useApi<AgreementFile[]>(`/resellers/${resellerId}/agreement-files`);
  const input = useRef<HTMLInputElement>(null);
  const action = useAction();
  return (
    <Card title="Agreement copy" subtitle="The signed consignment agreement (PDF or photo, up to 5 MB)" padded={false}
      actions={canEdit && <>
        <input ref={input} type="file" accept={AGREEMENT_ACCEPT} className="sr-only" aria-label="Agreement copy file"
          onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f && await action.run(() => uploadAgreement(resellerId, f))) reload(); }} />
        <Button size="sm" disabled={action.busy} onClick={() => input.current?.click()}><Upload aria-hidden />{action.busy ? "Uploading…" : "Upload copy"}</Button>
      </>}>
      <div className="px-5 pt-3"><Alert>{action.error}</Alert></div>
      {data && data.length === 0 && <EmptyState compact title="No copy attached" description="Upload the signed agreement so everyone can find it." />}
      <ul className="divide-y divide-line">
        {(data ?? []).map((f) => (
          <li key={f.id} className="flex items-center gap-3 px-5 py-3 text-label">
            <FileText className="size-4 shrink-0 text-ink-muted" aria-hidden />
            <a className="link min-w-0 flex-1 truncate" href={`/api/resellers/${resellerId}/agreement-files/${f.id}`} target="_blank" rel="noreferrer">{f.filename}</a>
            <span className="shrink-0 text-caption text-ink-muted">{Math.max(1, Math.round(f.size_bytes / 1024))} KB · {fmtDateTime(f.uploaded_at)}{f.uploaded_by ? ` · ${f.uploaded_by}` : ""}</span>
            {canEdit && <Button size="sm" variant="ghost" aria-label={`Remove ${f.filename}`}
              onClick={async () => { if (await action.run(() => api.del(`/resellers/${resellerId}/agreement-files/${f.id}`))) reload(); }}><Trash2 aria-hidden /></Button>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
