"use client";

import { Bell, CheckCheck, MonitorUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AppNotification } from "@/lib/types";
import { useNotifications } from "./NotificationCenter";
import { cx, EmptyState } from "./ui";

/** In-app notifications (stock requests, sales, deliveries…). The count comes from NotificationCenter (one poll). */
export function NotificationBell() {
  const router = useRouter();
  const { unread, refresh, bellOpen: open, setBellOpen: setOpen, desktop, enableDesktop } = useNotifications();
  const { data: items, reload } = useApi<AppNotification[]>(open ? "/notifications" : null, { limit: 15 });
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, setOpen]);

  async function openItem(n: AppNotification) {
    setOpen(false);
    if (!n.read_at) { await api.post(`/notifications/${n.id}/read`).catch(() => undefined); refresh(); }
    if (n.link) router.push(n.link);
  }

  async function readAll() {
    await api.post("/notifications/read-all").catch(() => undefined);
    reload();
    refresh();
  }

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="dialog"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        className="relative touch-target rounded-control p-2 text-ink-secondary transition hover:bg-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-ink">
        <Bell className="size-4.5" aria-hidden />
        {unread > 0 && <span className="absolute top-1 right-1 size-4.5 animate-ping rounded-full bg-brand/70" aria-hidden />}
        {unread > 0 && (
          <span className="num absolute top-1 right-1 inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-brand px-1 text-caption font-semibold text-ink">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications" className="absolute right-0 z-40 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-card border border-line bg-surface shadow-pop">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="text-body font-semibold text-ink">Notifications</span>
            {unread > 0 && (
              <button type="button" onClick={readAll} className="inline-flex items-center gap-1 text-caption font-medium text-ink-secondary hover:text-ink">
                <CheckCheck className="size-3.5" aria-hidden />Mark all read
              </button>
            )}
          </div>
          {desktop === "default" && (
            <button type="button" onClick={enableDesktop}
              className="flex w-full items-center gap-2 border-b border-line bg-subtle px-4 py-2 text-left text-caption font-medium text-ink-secondary hover:text-ink">
              <MonitorUp className="size-3.5" aria-hidden />Turn on desktop alerts
            </button>
          )}
          <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto">
            {items?.length === 0 && <li><EmptyState compact title="No notifications" description="Updates on stock requests appear here." /></li>}
            {!items && <li className="px-4 py-6 text-center text-label text-ink-muted">Loading…</li>}
            {items?.map((n) => (
              <li key={n.id}>
                <button type="button" onClick={() => openItem(n)}
                  className={cx("flex w-full gap-3 px-4 py-3 text-left transition hover:bg-subtle", !n.read_at && "bg-brand-soft/60")}>
                  <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-brand-text")} aria-hidden />
                  <span className="min-w-0">
                    <span className={cx("block text-label", n.read_at ? "text-ink-secondary" : "font-medium text-ink")}>{n.title}</span>
                    {n.body && <span className="mt-0.5 block line-clamp-2 text-caption text-ink-muted">{n.body}</span>}
                    <span className="mt-0.5 block text-caption text-ink-muted">{fmtDateTime(n.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
