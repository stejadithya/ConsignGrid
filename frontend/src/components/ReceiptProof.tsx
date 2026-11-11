"use client";

import { Camera, X } from "lucide-react";
import { useRef, useState } from "react";
import { compressPhoto, dataUrlKb } from "@/lib/image";
import type { Me } from "@/lib/types";
import { Field, Input, Textarea } from "./ui";

export interface Receipt { receivedBy: string; notes: string; photos: string[] }
export const blankReceipt = (): Receipt => ({ receivedBy: "", notes: "", photos: [] });
const MAX_PHOTOS = 3;

/** A Sales Rep handing stock over must record who took it and a short note. */
export const handoverRequired = (user: Me | null) => user?.role === "SALES_REP";
export const receiptReady = (r: Receipt, user: Me | null) =>
  !handoverRequired(user) || (r.receivedBy.trim().length >= 2 && r.notes.trim().length >= 3);
export const receiptBody = (r: Receipt) => ({
  received_by_name: r.receivedBy.trim() || null, notes: r.notes.trim() || null, photos: r.photos,
});

/** Stock carried by a Sales Rep is confirmed only by the receiving dealer or that Sales Rep. */
export function canConfirmCarried(user: Me | null, carriedByUserId: number | null | undefined) {
  if (!user) return false;
  if (user.reseller_id) return true;
  return !carriedByUserId || user.id === carriedByUserId;
}

/** Received by, hand-over notes and up to three drop-off photos (compressed on the phone before upload). */
export function ReceiptFields({ value, onChange, user, showNotes = true }: {
  value: Receipt; onChange: (r: Receipt) => void; user: Me | null; showNotes?: boolean;
}) {
  const required = handoverRequired(user);
  return (
    <div className="space-y-3">
      <Field label="Received by" required={required}
        hint={required ? "Name of the person at the dealer who took the tyres." : "Optional: who took the tyres."}>
        {(id) => <Input id={id} value={value.receivedBy} maxLength={120} placeholder="e.g. Ravi (owner)"
          onChange={(e) => onChange({ ...value, receivedBy: e.target.value })} />}
      </Field>
      {showNotes && (
        <Field label={required ? "Hand-over notes" : "Notes"} required={required}
          hint={required ? "Who was there, anything worth remembering if questions come up later." : undefined}>
          {(id) => <Textarea id={id} rows={2} value={value.notes} placeholder="e.g. Handed to Ravi at the counter, owner present"
            onChange={(e) => onChange({ ...value, notes: e.target.value })} />}
        </Field>
      )}
      <PhotoPicker photos={value.photos} onChange={(photos) => onChange({ ...value, photos })} />
    </div>
  );
}

/** Up to three photos, compressed on the phone before upload. Used at drop-off and at collection. */
export function PhotoPicker({ photos, onChange, label = "Photo at drop-off", alt = "Drop-off photo" }: {
  photos: string[]; onChange: (photos: string[]) => void; label?: string; alt?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      const room = MAX_PHOTOS - photos.length;
      const added = await Promise.all([...files].slice(0, room).map(compressPhoto));
      onChange([...photos, ...added]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the photo");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-label font-medium text-ink">{label} <span className="font-normal text-ink-muted">(optional, up to {MAX_PHOTOS})</span></div>
      <div className="flex flex-wrap items-center gap-2">
        {photos.map((p, i) => (
          <div key={i} className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p} alt={`${alt} ${i + 1}`} className="size-16 rounded-md border border-line object-cover" />
            <button type="button" aria-label={`Remove photo ${i + 1}`} onClick={() => onChange(photos.filter((_, j) => j !== i))}
              className="absolute -top-1.5 -right-1.5 rounded-full bg-ink p-0.5 text-white"><X className="size-3" aria-hidden /></button>
            <span className="block text-center text-caption text-ink-muted">{dataUrlKb(p)} KB</span>
          </div>
        ))}
        {photos.length < MAX_PHOTOS && (
          <label className="flex h-16 cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-line-strong px-3 text-label text-ink-secondary hover:bg-subtle">
            <Camera className="size-4" aria-hidden />{busy ? "Processing…" : "Take photo"}
            <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" disabled={busy}
              onChange={(e) => add(e.target.files)} />
          </label>
        )}
      </div>
      {error && <p className="mt-1 text-caption text-danger">{error}</p>}
    </div>
  );
}

/** What was recorded at hand-over: who took it, notes and photos. */
export function ReceiptView({ receivedBy, notes, photos, retired }: {
  receivedBy?: string | null; notes?: string | null; photos?: number[]; retired?: number;
}) {
  if (!receivedBy && !notes && !photos?.length && !retired) return null;
  return (
    <div className="space-y-1.5 text-label">
      {receivedBy && <div><span className="text-ink-muted">Received by</span> <b className="font-medium">{receivedBy}</b></div>}
      {notes && <div className="text-ink-secondary">{notes}</div>}
      {!!photos?.length && (
        <div className="flex flex-wrap gap-1.5">
          {photos.map((id) => (
            <a key={id} href={`/api/proofs/photos/${id}`} target="_blank" rel="noreferrer" title="Open photo">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/api/proofs/photos/${id}`} alt="Drop-off photo" loading="lazy" className="size-14 rounded-md border border-line object-cover" />
            </a>
          ))}
        </div>
      )}
      {!!retired && <div className="text-caption text-ink-muted">{retired} photo{retired === 1 ? "" : "s"} archived under the photo archiving setting</div>}
    </div>
  );
}
