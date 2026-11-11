import { describe, expect, it } from "vitest";
import { withQuery } from "./api";
import { fmtMoney, humanize } from "./format";

describe("withQuery", () => {
  it("omits empty values and repeats arrays", () => {
    expect(withQuery("/x", { a: 1, b: "", c: undefined, d: null, t: ["WAREHOUSE", "CONSIGNMENT"] }))
      .toBe("/x?a=1&t=WAREHOUSE&t=CONSIGNMENT");
    expect(withQuery("/x")).toBe("/x");
  });
});

describe("formatting", () => {
  it("formats money from decimal strings without float surprises", () => {
    expect(fmtMoney("1320.00")).toMatch(/1,?320\.00/);
    expect(fmtMoney(null)).toBe("—");
  });
  it("humanizes enum codes", () => {
    expect(humanize("RECEIVED_WITH_DISCREPANCY")).toBe("Received with discrepancy");
  });
});
