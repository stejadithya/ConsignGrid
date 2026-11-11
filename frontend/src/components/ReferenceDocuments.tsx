"use client";

import { ExternalLink, FileImage, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";
import { fmtDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Button, buttonClass, Card, cx, Modal } from "./ui";

export interface ReferenceDocument {
  id: string;
  title: string;
  description: string;
  effective_date: string;
  media_type: string;
  width: number;
  height: number;
  url: string;
}

/**
 * Reference documents (e.g. the dealer price list). Served by the authenticated API — never as public files —
 * because they can be commercially confidential. They are references only and never create products or stock.
 */
export function ReferenceDocuments() {
  const { data } = useApi<ReferenceDocument[]>("/reference-documents");
  const [open, setOpen] = useState<ReferenceDocument | null>(null);
  if (!data?.length) return null;
  return (
    <>
      <Card title="Reference documents" subtitle="For reference only — product records come from the product import, not from these documents" padded={false} className="mb-6">
        <ul className="divide-y divide-line">
          {data.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
              <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-control bg-brand-soft text-brand-text"><FileImage className="size-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-ink">{d.title}</div>
                <div className="text-label text-ink-muted">Effective {fmtDate(d.effective_date)} · {d.description}</div>
              </div>
              <Button size="sm" onClick={() => setOpen(d)} aria-label={`View ${d.title}`}>View</Button>
            </li>
          ))}
        </ul>
      </Card>
      {open && <DocumentViewer doc={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function DocumentViewer({ doc, onClose }: { doc: ReferenceDocument; onClose: () => void }) {
  const [zoom, setZoom] = useState(false);
  return (
    <Modal open wide title={doc.title} description={`Effective ${fmtDate(doc.effective_date)}`} onClose={onClose}
      footer={<>
        <Button onClick={() => setZoom((z) => !z)}>{zoom ? <><ZoomOut aria-hidden />Fit to window</> : <><ZoomIn aria-hidden />Actual size</>}</Button>
        <a href={doc.url} target="_blank" rel="noopener noreferrer"
          className={buttonClass()}>
          <ExternalLink className="size-4" aria-hidden />Open in new tab
        </a>
        <Button variant="primary" onClick={onClose}>Close</Button>
      </>}>
      <div className={cx("rounded-control border border-line bg-subtle", zoom ? "max-h-[75vh] overflow-auto" : "flex justify-center")}>
        {/* Authenticated API image: plain <img> so the session cookie is sent; aspect ratio always preserved. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={doc.url} alt={doc.title} width={doc.width} height={doc.height}
          className={zoom ? "h-auto w-auto max-w-none cursor-zoom-out" : "h-auto max-h-[70vh] w-auto max-w-full cursor-zoom-in object-contain"}
          onClick={() => setZoom((z) => !z)} />
      </div>
    </Modal>
  );
}
