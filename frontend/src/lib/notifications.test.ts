import { describe, expect, it } from "vitest";
import { capToasts, newItems, titleWithCount, type Toast } from "./notifications";

describe("notification centre helpers", () => {
  it("finds only items newer than the last seen id, newest first", () => {
    const items = [{ id: 4 }, { id: 9 }, { id: 7 }, { id: 2 }];
    expect(newItems(4, items).map((n) => n.id)).toEqual([9, 7]);
    expect(newItems(9, items)).toEqual([]);
    expect(newItems(0, items).map((n) => n.id)).toEqual([9, 7, 4, 2]);
  });

  it("caps the toasts at three and counts the rest", () => {
    const t = (k: number): Toast => ({ key: String(k), title: `N${k}` });
    expect(capToasts([t(1), t(2)])).toEqual({ visible: [t(1), t(2)], more: 0 });
    const many = [t(5), t(4), t(3), t(2), t(1)];
    const capped = capToasts(many);
    expect(capped.visible.map((x) => x.key)).toEqual(["5", "4", "3"]);
    expect(capped.more).toBe(2);
  });

  it("prefixes the tab title with the unread count", () => {
    expect(titleWithCount("TyreGrow", 3)).toBe("(3) TyreGrow");
    expect(titleWithCount("(3) TyreGrow", 5)).toBe("(5) TyreGrow");
    expect(titleWithCount("(5) TyreGrow", 0)).toBe("TyreGrow");
    expect(titleWithCount("TyreGrow", 120)).toBe("(99+) TyreGrow");
    expect(titleWithCount("(99+) TyreGrow", 1)).toBe("(1) TyreGrow");
  });
});
