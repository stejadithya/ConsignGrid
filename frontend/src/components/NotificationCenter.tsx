"use client";

/**
 * One place that watches for new notifications (finding 4): it polls, shows pop-up toasts with a short chime,
 * pulses the bell, prefixes the tab title with the unread count and, when allowed, shows desktop alerts.
 * NotificationBell reads from here, so there is only one poll.
 */

import { BellRing, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { AppNotification } from "@/lib/types";
import { capToasts, newItems, titleWithCount, type Toast } from "@/lib/notifications";
import { cx } from "./ui";

const POLL_MS = 20_000;
const TOAST_MS = 15_000;
const SOUND_KEY = "tyregrow.notificationSound";

interface Centre {
  unread: number;
  refresh: () => void;
  bellOpen: boolean;
  setBellOpen: (open: boolean) => void;
  soundOn: boolean;
  setSoundOn: (on: boolean) => void;
  desktop: NotificationPermission | "unsupported";
  enableDesktop: () => void;
  markRead: (id: number) => Promise<void>;
}

const Ctx = createContext<Centre | null>(null);

export function useNotifications(): Centre {
  const c = useContext(Ctx);
  if (!c) throw new Error("useNotifications must be used inside NotificationCenter");
  return c;
}

function readSound(): boolean {
  try { return window.localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; }
}

function writeSound(on: boolean) {
  try { window.localStorage.setItem(SOUND_KEY, on ? "on" : "off"); } catch { /* storage unavailable: keep in memory */ }
}

function desktopPermission(): NotificationPermission | "unsupported" {
  return typeof window !== "undefined" && "Notification" in window ? window.Notification.permission : "unsupported";
}

/** A short two-note chime made with WebAudio (no sound file). Silently does nothing if audio is blocked. */
function chime() {
  try {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const now = ctx.currentTime;
    [[880, 0], [1320, 0.12]].forEach(([freq, at]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + at);
      gain.gain.exponentialRampToValueAtTime(0.18, now + at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.3);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + at);
      osc.stop(now + at + 0.32);
    });
    setTimeout(() => ctx.close().catch(() => undefined), 800);
  } catch { /* audio not available */ }
}

export function NotificationCenter({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [bellOpen, setBellOpen] = useState(false);
  const [soundOn, setSoundState] = useState(true);
  const [desktop, setDesktop] = useState<NotificationPermission | "unsupported">("unsupported");
  const lastSeen = useRef<number | null>(null);   // null until the first poll
  const soundRef = useRef(true);

  const poll = useCallback(async () => {
    let count: { unread: number; latest_id: number };
    try { count = await api.get("/notifications/unread-count"); } catch { return; }
    setUnread(count.unread);
    if (lastSeen.current === null) {
      // First load: one summary toast instead of one per old notification.
      lastSeen.current = count.latest_id;
      if (count.unread > 0) {
        setToasts([{ key: "summary", title: `You have ${count.unread} unread notification${count.unread === 1 ? "" : "s"}` }]);
      }
      return;
    }
    if (count.latest_id <= lastSeen.current) return;
    let items: AppNotification[];
    try { items = await api.get("/notifications", { after_id: lastSeen.current, limit: 20 }); } catch { return; }
    const fresh = newItems(lastSeen.current, items);
    lastSeen.current = count.latest_id;
    if (!fresh.length) return;
    setToasts((old) => [
      ...fresh.map((n) => ({ key: `n${n.id}`, title: n.title, body: n.body, link: n.link, notificationId: n.id })),
      ...old.filter((t) => t.key !== "summary"),
    ]);
    if (soundRef.current) chime();
    if (document.hidden && desktopPermission() === "granted") {
      try {
        const top = fresh[0];
        const note = new window.Notification(fresh.length > 1 ? `${top.title} (+${fresh.length - 1} more)` : top.title,
          { body: top.body ?? undefined, tag: `tyregrow-${top.id}` });
        note.onclick = () => { window.focus(); if (top.link) router.push(top.link); };
      } catch { /* desktop alerts unavailable */ }
    }
  }, [router]);

  // Settings that live in the browser are read once mounted.
  useEffect(() => {
    const t = setTimeout(() => {
      const on = readSound();
      soundRef.current = on;
      setSoundState(on);
      setDesktop(desktopPermission());
    }, 0);
    return () => clearTimeout(t);
  }, []);

  // Poll every 20 seconds, on every page change and when the window regains focus.
  useEffect(() => {
    const first = setTimeout(poll, 0);
    const t = setInterval(poll, POLL_MS);
    const onFocus = () => { poll(); };
    window.addEventListener("focus", onFocus);
    return () => { clearTimeout(first); clearInterval(t); window.removeEventListener("focus", onFocus); };
  }, [poll]);
  useEffect(() => {
    const t = setTimeout(poll, 0);
    return () => clearTimeout(t);
  }, [pathname, poll]);

  // "(3) TyreGrow": keep the tab title prefixed while anything is unread (re-applied after page changes).
  useEffect(() => {
    const apply = () => { document.title = titleWithCount(document.title, unread); };
    apply();
    const t = setTimeout(apply, 300);
    return () => clearTimeout(t);
  }, [unread, pathname]);

  const dismiss = useCallback((key: string) => setToasts((all) => all.filter((t) => t.key !== key)), []);
  const markRead = useCallback(async (id: number) => {
    await api.post(`/notifications/${id}/read`).catch(() => undefined);
    poll();
  }, [poll]);

  const value = useMemo<Centre>(() => ({
    unread, refresh: poll, bellOpen, setBellOpen, soundOn, markRead,
    setSoundOn: (on: boolean) => { soundRef.current = on; setSoundState(on); writeSound(on); if (on) chime(); },
    desktop,
    enableDesktop: () => {
      if (desktopPermission() === "unsupported") return;
      window.Notification.requestPermission().then(setDesktop).catch(() => undefined);
    },
  }), [unread, poll, bellOpen, soundOn, desktop, markRead]);

  async function open(t: Toast) {
    dismiss(t.key);
    if (t.notificationId) await markRead(t.notificationId);
    if (t.link) router.push(t.link);
    else setBellOpen(true);
  }

  return (
    <Ctx.Provider value={value}>
      {children}
      <Toasts toasts={toasts} onOpen={open} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

/** Phones: one notification at a time, docked at the bottom (above a sticky action bar and the home indicator) so it
 *  never covers the page title or its actions. Tablets (touch screens, and anything under 1024px): up to three, bottom
 *  right, above the action bar, clear of the header buttons. Desktop with a mouse: up to three, top right. */
function Toasts({ toasts, onOpen, onDismiss }: { toasts: Toast[]; onOpen: (t: Toast) => void; onDismiss: (key: string) => void }) {
  const { visible, more } = capToasts(toasts);
  const morePhone = more + Math.max(0, visible.length - 1);
  const pill = "pointer-events-auto self-end rounded-pill border border-line bg-surface px-3 py-1 text-caption font-medium text-ink-secondary shadow-card";
  return (
    <div role="status" aria-live="polite" aria-label="New notifications"
      className="no-print pointer-events-none fixed inset-x-3 bottom-dock z-[60] flex flex-col gap-2 sm:inset-x-auto sm:right-5 sm:w-[22rem] lg:pointer-fine:top-16 lg:pointer-fine:bottom-auto">
      {visible.map((t, i) => <ToastCard key={t.key} toast={t} onOpen={onOpen} onDismiss={onDismiss} className={i > 0 ? "max-sm:hidden" : undefined} />)}
      {morePhone > 0 && <div aria-hidden className={cx(pill, "sm:hidden")}>+{morePhone} more</div>}
      {more > 0 && <div className={cx(pill, "max-sm:hidden")}>+{more} more</div>}
    </div>
  );
}

function ToastCard({ toast, onOpen, onDismiss, className }: { toast: Toast; onOpen: (t: Toast) => void; onDismiss: (key: string) => void; className?: string }) {
  const [hovered, setHovered] = useState(false);
  // Auto-hide after 15 seconds, but never while the pointer is over the toast.
  useEffect(() => {
    if (hovered) return;
    const t = setTimeout(() => onDismiss(toast.key), TOAST_MS);
    return () => clearTimeout(t);
  }, [hovered, toast.key, onDismiss]);
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className={cx("pointer-events-auto flex gap-3 rounded-card border border-line bg-surface p-3.5 shadow-pop", className)}>
      <BellRing className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="text-label font-semibold text-ink">{toast.title}</div>
        {toast.body && <div className="mt-0.5 line-clamp-2 text-caption text-ink-secondary">{toast.body}</div>}
        <div className="mt-2 flex gap-3 text-caption font-medium">
          <button type="button" className="relative touch-target text-ink underline-offset-2 hover:underline" onClick={() => onOpen(toast)}>Open</button>
          <button type="button" className="relative touch-target text-ink-muted hover:text-ink" onClick={() => onDismiss(toast.key)}>Dismiss</button>
        </div>
      </div>
      <button type="button" onClick={() => onDismiss(toast.key)} aria-label="Dismiss notification"
        className="relative touch-target -m-1 self-start rounded-md p-1 text-ink-muted hover:bg-subtle hover:text-ink">
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}
