"use client";

import { ChevronDown, ChevronRight, KeyRound, LogOut, Menu, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, Sparkles, Volume2, VolumeX, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { branding } from "@/config/branding";
import { useAuth } from "@/lib/auth";
import { navFor, type NavGroup } from "@/config/roles";
import type { Me } from "@/lib/types";
import { FeedbackDialog } from "./FeedbackDialog";
import { NotificationBell } from "./NotificationBell";
import { GlobalSearch } from "./GlobalSearch";
import { NotificationCenter, useNotifications } from "./NotificationCenter";
import { Logo } from "./Logo";
import { PasswordForm } from "./PasswordForm";
import { Avatar, cx, Loading, Modal, Skeleton } from "./ui";

// Deferred features sit under "Coming later" instead of appearing as dead links.
const COMING_LATER = ["Email notifications", "Credit notes & returns", "Forecasting & analytics"];

function visibleNav(user: Me, can: (p: string) => boolean): NavGroup[] {
  return navFor(user.role, user.reseller_id)
    .map(({ group, items }) => ({ group, items: items.filter((n) => !n.permission || can(n.permission)) }))
    .filter((g) => g.items.length);
}

const hrefPath = (href: string) => href.split("?")[0];
const matches = (pathname: string, href: string) => {
  const path = hrefPath(href);
  return path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(`${path}/`);
};
/** The most specific nav entry for the page (e.g. /stock-requests/pending beats /stock-requests). */
const activeHref = (groups: NavGroup[], pathname: string) =>
  groups.flatMap((g) => g.items).filter((n) => matches(pathname, n.href))
    .sort((a, b) => hrefPath(b.href).length - hrefPath(a.href).length)[0]?.href;

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, can } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  // The mobile menu closes on navigation because it is only "open" for the path it was opened on.
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const menuOpen = menuFor === pathname;
  // Tablet landscape (1024–1279px): the sidebar is a 64px icon rail; expanded it shows labels over the page, and it
  // collapses again on navigation, Escape or a tap outside.
  const [railFor, setRailFor] = useState<string | null>(null);
  const railOpen = railFor === pathname;
  const railRef = useRef<HTMLElement>(null);
  const railToggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!railOpen) return;
    const onDown = (e: PointerEvent) => { if (!railRef.current?.contains(e.target as Node)) setRailFor(null); };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [railOpen]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (user?.must_change_password) return <ForcePasswordChange />;

  if (loading || !user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-5" role="status">
        <Logo className="h-8" priority />
        <Skeleton className="h-1.5 w-40" />
        <span className="sr-only">Checking session…</span>
      </div>
    );
  }

  const groups = visibleNav(user, can);

  return (
    <NotificationCenter>
    <div className="min-h-screen lg:flex">
      <div className="no-print hidden shrink-0 lg:block lg:w-16 xl:w-64">
        <aside ref={railRef} aria-label="Navigation"
          onKeyDown={(e) => { if (e.key === "Escape" && railOpen) { setRailFor(null); railToggle.current?.focus(); } }}
          className={cx("sticky top-0 z-40 flex h-screen flex-col border-r border-line bg-surface", railOpen ? "w-64 shadow-pop xl:shadow-none" : "w-16 xl:w-64")}>
          <Sidebar groups={groups} pathname={pathname} rail={{ open: railOpen, toggle: () => setRailFor(railOpen ? null : pathname) }} toggleRef={railToggle} />
        </aside>
      </div>

      {menuOpen && (
        <div className="no-print fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMenuFor(null)} aria-hidden />
          <div className="relative flex h-full w-72 max-w-[85vw] flex-col bg-surface shadow-pop">
            <button type="button" onClick={() => setMenuFor(null)} aria-label="Close menu"
              className="absolute top-4 right-3 touch-target rounded-md p-1.5 text-ink-muted hover:bg-subtle hover:text-ink">
              <X className="size-4" aria-hidden />
            </button>
            <Sidebar groups={groups} pathname={pathname} />
          </div>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="no-print sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6 lg:px-8">
          <button type="button" className="relative touch-target -ml-1 rounded-md p-1.5 text-ink-secondary hover:bg-subtle lg:hidden" onClick={() => setMenuFor(pathname)}
            aria-expanded={menuOpen} aria-label="Open menu">
            <Menu className="size-5" aria-hidden />
          </button>
          <Link href="/" className="lg:hidden" aria-label={`${branding.productName} home`}><Logo className="h-5" /></Link>
          <Breadcrumb groups={groups} pathname={pathname} />
          <div className="ml-auto flex min-w-0 items-center gap-1.5"><GlobalSearch /><NotificationBell /><UserMenu user={user} /></div>
        </header>
        {/* The bottom padding grows by the height of a sticky MobileActionBar, so it never covers the end of the page. */}
        <main className="mx-auto w-full max-w-content px-page pt-6 pb-[calc(1.5rem+var(--action-bar-height))] lg:pt-8 lg:pb-[calc(2rem+var(--action-bar-height))]">
          <Suspense fallback={<Loading />}>{children}</Suspense>
        </main>
      </div>
    </div>
    </NotificationCenter>
  );
}

/** The navigation list. `rail` (the desktop sidebar): between 1024 and 1279px it is an icon rail unless expanded;
 *  each icon keeps its label for screen readers and as a tooltip. The phone drawer passes no rail. */
function Sidebar({ groups, pathname, rail, toggleRef }: {
  groups: NavGroup[]; pathname: string; rail?: { open: boolean; toggle: () => void }; toggleRef?: RefObject<HTMLButtonElement | null>;
}) {
  const current = activeHref(groups, pathname);
  // Classes that only apply to the collapsed rail (1024–1279px).
  const compact = (cls: string) => (rail && !rail.open ? cls : "");
  return (
    <>
      <div className={cx("flex items-start justify-between gap-2 px-5 pt-5 pb-4", compact("lg:max-xl:justify-center lg:max-xl:px-2 lg:max-xl:pt-3 lg:max-xl:pb-2"))}>
        <div className={compact("lg:max-xl:hidden")}>
          <Link href="/" className="inline-block rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink" aria-label={`${branding.productName} home`}>
            <Logo className="h-6.5" priority />
          </Link>
          <div className="mt-1.5 text-caption font-medium tracking-wider text-ink-muted uppercase">{branding.descriptor}</div>
        </div>
        {rail && (
          <button ref={toggleRef} type="button" onClick={rail.toggle} aria-expanded={rail.open} aria-controls="main-nav"
            aria-label={rail.open ? "Collapse navigation" : "Expand navigation"} title={rail.open ? "Collapse navigation" : "Expand navigation"}
            className="hidden size-11 shrink-0 items-center justify-center rounded-md text-ink-secondary hover:bg-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-ink lg:max-xl:inline-flex">
            {rail.open ? <PanelLeftClose className="size-5" aria-hidden /> : <PanelLeftOpen className="size-5" aria-hidden />}
          </button>
        )}
      </div>
      <nav id={rail ? "main-nav" : undefined} className={cx("flex-1 overflow-y-auto px-3 pb-4", compact("lg:max-xl:px-2"))} aria-label="Main">
        {groups.map(({ group, items }) => (
          <div key={group} className={cx("mt-4 first:mt-1", compact("lg:max-xl:mt-2 lg:max-xl:border-t lg:max-xl:border-line lg:max-xl:pt-2 lg:max-xl:first:border-0"))}>
            <div className={cx("px-2.5 pb-1.5 text-caption font-medium tracking-wider text-ink-muted uppercase", compact("lg:max-xl:sr-only"))}>{group}</div>
            <ul className="space-y-0.5">
              {items.map((n) => {
                const active = n.href === current;
                return (
                  <li key={n.href}>
                    <Link href={n.href} aria-current={active ? "page" : undefined} title={rail && !rail.open ? n.label : undefined}
                      className={cx("group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-body transition-colors",
                        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink",
                        compact("lg:max-xl:h-11 lg:max-xl:justify-center lg:max-xl:px-0"),
                        active ? "bg-brand-soft font-semibold text-ink" : "text-ink-secondary hover:bg-neutral-soft hover:text-ink active:bg-line")}>
                      {active && <span className={cx("absolute top-1.5 bottom-1.5 -left-3 w-0.75 rounded-r-full bg-brand", compact("lg:max-xl:-left-2"))} aria-hidden />}
                      <n.icon className={cx("size-4.5 shrink-0", compact("lg:max-xl:size-5"), active ? "text-ink" : "text-ink-muted group-hover:text-ink-secondary")} aria-hidden />
                      <span className={compact("lg:max-xl:sr-only")}>{n.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <details className={cx("group border-t border-line px-5 py-3 text-caption", compact("lg:max-xl:hidden"))}>
        <summary className="flex cursor-pointer list-none items-center gap-2 text-ink-muted hover:text-ink-secondary [&::-webkit-details-marker]:hidden">
          <Sparkles className="size-3.5" aria-hidden /> Coming later
          <ChevronRight className="ml-auto size-3.5 transition group-open:rotate-90" aria-hidden />
        </summary>
        <ul className="mt-2 space-y-1 pl-5.5 text-ink-muted">
          {COMING_LATER.map((d) => <li key={d}>{d}</li>)}
        </ul>
      </details>
    </>
  );
}

function Breadcrumb({ groups, pathname }: { groups: NavGroup[]; pathname: string }) {
  let trail: string[] = [];
  const current = activeHref(groups, pathname);
  for (const g of groups) {
    const item = g.items.find((n) => n.href === current);
    if (item) {
      trail = [g.group, item.label];
      const path = hrefPath(item.href);
      const rest = pathname.slice(path.length).split("/").filter(Boolean);
      if (rest.length && path !== "/" && pathname !== path) trail.push(rest[0] === "new" ? "New" : "Details");
      break;
    }
  }
  if (!trail.length) return null;
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-label text-ink-muted md:flex">
      {trail.map((t, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="size-3.5" aria-hidden />}
          <span className={i === trail.length - 1 ? "font-medium text-ink" : ""}>{t}</span>
        </span>
      ))}
    </nav>
  );
}

function UserMenu({ user }: { user: Me }) {
  const { logout, can } = useAuth();
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<null | "feedback" | "password">(null);
  const { soundOn, setSoundOn } = useNotifications();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu" aria-label={`Account menu for ${user.full_name}`}
        className="relative touch-target flex items-center gap-2.5 rounded-control py-1 pr-1.5 pl-1 text-left transition hover:bg-subtle focus-visible:outline-2 focus-visible:outline-ink">
        <Avatar name={user.full_name} />
        <span className="hidden leading-tight sm:block">
          <span className="block text-label font-medium text-ink">{user.full_name}</span>
          <span className="block text-caption text-ink-muted">{user.role_label}</span>
        </span>
        <ChevronDown className="size-4 text-ink-muted" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-64 overflow-hidden rounded-card border border-line bg-surface shadow-pop">
          <div className="flex items-center gap-3 border-b border-line px-4 py-3">
            <Avatar name={user.full_name} size="lg" />
            <div className="min-w-0">
              <div className="truncate text-body font-medium text-ink">{user.full_name}</div>
              <div className="truncate text-caption text-ink-muted">{user.email}</div>
              <div className="mt-1 inline-flex rounded-full bg-neutral-soft px-2 text-caption leading-5 font-medium text-ink-secondary">{user.role_label}</div>
            </div>
          </div>
          <div className="p-1.5">
            {can("feedback.submit") && (
              <button type="button" role="menuitem" onClick={() => { setOpen(false); setDialog("feedback"); }}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-body text-ink-secondary hover:bg-subtle hover:text-ink">
                <MessageSquarePlus className="size-4" aria-hidden /> Pilot feedback
              </button>
            )}
            <button type="button" role="menuitem" onClick={() => setSoundOn(!soundOn)}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-body text-ink-secondary hover:bg-subtle hover:text-ink">
              {soundOn ? <Volume2 className="size-4" aria-hidden /> : <VolumeX className="size-4" aria-hidden />} Notification sound: {soundOn ? "on" : "off"}
            </button>
            <button type="button" role="menuitem" onClick={() => { setOpen(false); setDialog("password"); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-body text-ink-secondary hover:bg-subtle hover:text-ink">
              <KeyRound className="size-4" aria-hidden /> Change password
            </button>
            <button type="button" role="menuitem" onClick={logout}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-body text-ink-secondary hover:bg-subtle hover:text-ink">
              <LogOut className="size-4" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      )}
      {dialog === "feedback" && <FeedbackDialog onClose={() => setDialog(null)} />}
      {dialog === "password" && (
        <Modal open title="Change your password" description="Choose a new password for signing in to TyreGrow." onClose={() => setDialog(null)}>
          <PasswordForm onDone={() => setDialog(null)} />
        </Modal>
      )}
    </div>
  );
}

/** Shown instead of the app until a set-up or administrator-chosen password has been replaced. */
function ForcePasswordChange() {
  const { user, logout } = useAuth();
  return (
    <div className="flex min-h-screen items-start justify-center bg-canvas px-4 py-16">
      <div className="w-full max-w-md rounded-card border border-line bg-surface p-7 shadow-raised">
        <Logo className="h-7" priority />
        <h1 className="mt-6 text-display-compact font-bold">Choose your own password</h1>
        <p className="mt-1 mb-6 text-body text-ink-secondary">
          Welcome{user ? `, ${user.full_name.split(" ")[0]}` : ""}. You signed in with a temporary password. Set a personal
          password to continue.
        </p>
        <PasswordForm />
        <button type="button" onClick={logout} className="mt-4 text-label text-ink-muted hover:text-ink">Sign out</button>
      </div>
    </div>
  );
}
