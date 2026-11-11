import { afterEach, describe, expect, it } from "vitest";
import { ROLE_LABELS } from "@/config/roles";
import { humanize } from "./format";
import { DEFAULT_WORDS, resetWords, setWords, vocab } from "./terms";

afterEach(resetWords);

describe("Industry Pack vocabulary", () => {
  it("defaults to the tyres pack's words", () => {
    expect([vocab.item, vocab.Items, vocab.partner, vocab.Partners, vocab.site]).toEqual(["tyre", "Tyres", "dealer", "Dealers", "shop"]);
    expect([vocab.aPartner, vocab.ASite]).toEqual(["a dealer", "A shop"]);
  });

  it("switches every word, with the right article", () => {
    setWords({ item: "implant", items: "implants", partner: "hospital", partners: "hospitals", site: "theatre", sites: "theatres" });
    expect([vocab.Item, vocab.aItem, vocab.AItem, vocab.Partners, vocab.aSite]).toEqual(["Implant", "an implant", "An implant", "Hospitals", "a theatre"]);
  });

  it("ignores unknown keys and blank values", () => {
    setWords({ partner: "  ", colour: "red", site: "branch" });
    expect([vocab.partner, vocab.site]).toEqual([DEFAULT_WORDS.partner, "branch"]);
  });

  it("reaches labels defined outside components and humanised codes", () => {
    setWords({ partner: "stockist", partners: "stockists" });
    expect(ROLE_LABELS.RESELLER).toBe("Stockist");
    expect(humanize("RESELLER_REPORT")).toBe("Stockist report");
    expect(humanize("TWO_RESELLERS")).toBe("Two stockists");
  });
});
