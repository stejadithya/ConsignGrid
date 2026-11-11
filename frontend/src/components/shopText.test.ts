import { describe, expect, it } from "vitest";
import { shopText } from "./pickers";

describe("shopText: dealer name first, never the code or the address", () => {
  it("names a dealer's shop by dealer, shop and city", () => {
    expect(shopText({ name: "Main shop", city: "Auckland", reseller_name: "Roskill Tyres" })).toBe("Roskill Tyres — Main shop (Auckland)");
  });
  it("doesn't repeat the dealer name when the shop is named after it", () => {
    expect(shopText({ name: "Roskill Tyres", city: "Auckland", reseller_name: "Roskill Tyres" })).toBe("Roskill Tyres (Auckland)");
  });
  it("doesn't repeat the dealer name when the shop name starts with it", () => {
    expect(shopText({ name: "Roskill Tyres — Henderson", city: "Auckland", reseller_name: "Roskill Tyres" })).toBe("Roskill Tyres — Henderson (Auckland)");
  });
  it("leaves the dealer out on screens about one dealer, and names a warehouse by its name", () => {
    expect(shopText({ name: "Henderson", city: "Auckland", reseller_name: "Roskill Tyres" }, false)).toBe("Henderson (Auckland)");
    expect(shopText({ name: "Central Warehouse", city: null, reseller_name: null })).toBe("Central Warehouse");
  });
});
