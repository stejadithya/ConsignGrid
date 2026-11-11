import { describe, expect, it } from "vitest";
import { matchesSearch, searchTokens } from "./search";

const tyre = "103294 CEAT EcoDrive 195/65R15 91H";

describe("matchesSearch", () => {
  it("finds a size however people type it", () => {
    for (const q of ["195/65", "195 65", "19565", "195-65", "195 65 15", "195/65R15", "195 65r15", " 195  65 "]) {
      expect(matchesSearch(tyre, q), q).toBe(true);
    }
  });

  it("needs every word, in any order, ignoring case", () => {
    expect(matchesSearch(tyre, "ecodrive 195")).toBe(true);
    expect(matchesSearch(tyre, "195 ECODRIVE")).toBe(true);
    expect(matchesSearch(tyre, "ecodrive 205")).toBe(false);
    expect(matchesSearch(tyre, "205/55")).toBe(false);
  });

  it("matches part of a SKU or number, and an empty query matches everything", () => {
    expect(matchesSearch(tyre, "1032")).toBe(true);
    expect(matchesSearch(tyre, "")).toBe(true);
    expect(searchTokens("195/65 R15")).toEqual(["195", "65", "r15"]);
  });

  it("with several texts, each word must sit inside one of them (a table row's columns)", () => {
    expect(matchesSearch(["Alpha Tyres", "195/65R15"], "alpha 195 65")).toBe(true);
    expect(matchesSearch(["Alpha Tyres", "205"], "s2")).toBe(false);     // not across "Tyres" | "205"
  });
});
