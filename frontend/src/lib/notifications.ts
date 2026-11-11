/** Pure helpers for the notification centre (unit-tested). */

export interface Toast {
  key: string;
  title: string;
  body?: string | null;
  link?: string | null;
  notificationId?: number;
}

export const MAX_TOASTS = 3;

/** Items the client has not seen yet: ids above the last seen id, newest first. */
export function newItems<T extends { id: number }>(lastSeenId: number, items: T[]): T[] {
  return items.filter((n) => n.id > lastSeenId).sort((a, b) => b.id - a.id);
}

/** The toasts to show (newest first, at most `max`) and how many more are waiting. */
export function capToasts(toasts: Toast[], max = MAX_TOASTS): { visible: Toast[]; more: number } {
  return { visible: toasts.slice(0, max), more: Math.max(0, toasts.length - max) };
}

/** "(3) TyreGrow" from "TyreGrow" or "(1) TyreGrow"; the prefix is removed when nothing is unread. */
export function titleWithCount(title: string, unread: number): string {
  const bare = title.replace(/^\(\d+\+?\)\s/, "");
  return unread > 0 ? `(${unread > 99 ? "99+" : unread}) ${bare}` : bare;
}
