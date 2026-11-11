"use client";

/** Messages from TyreGrow on the dealer dashboard (finding 21): recent order updates, kindly worded. */

import { MessageCircle } from "lucide-react";
import Link from "next/link";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AppNotification } from "@/lib/types";
import { Card } from "../ui";

export function DealerMessages({ actions }: { actions?: (n: AppNotification) => React.ReactNode }) {
  const { data } = useApi<AppNotification[]>("/notifications", { limit: 50 });
  const messages = (data ?? []).filter((n) => n.title.startsWith("Update on your order")).slice(0, 5);
  if (!messages.length) return null;
  return (
    <Card title="Messages from TyreGrow" subtitle="Updates on your orders" padded={false} className="mb-6">
      <ul className="divide-y divide-line">
        {messages.map((n) => (
          <li key={n.id} className="flex gap-3 px-5 py-3.5">
            <MessageCircle className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                {n.link ? <Link className="link text-body font-medium" href={n.link}>{n.title}</Link> : <span className="text-body font-medium">{n.title}</span>}
                <time className="text-caption text-ink-muted" dateTime={n.created_at}>{fmtDateTime(n.created_at)}</time>
              </div>
              {n.body && <p className="mt-0.5 text-label text-ink-secondary">{n.body}</p>}
              {actions && <div className="mt-2">{actions(n)}</div>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
