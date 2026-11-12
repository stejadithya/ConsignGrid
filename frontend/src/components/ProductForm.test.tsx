import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StaticConfigProvider, type PublicConfig } from "@/lib/config";
import { resetWords } from "@/lib/terms";
import { ProductFormModal } from "./ProductForm";

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); resetWords(); });

const medical: PublicConfig = {
  brand: { product_name: "MediLoop", company_name: "Southern Ortho", support_email: "" },
  industry: {
    code: "medical", name: "Medical devices and implants", description: "", search_example: "e.g. a REF",
    brand_label: "Manufacturer", name_label: "Device", spec_label: "Spec", tyre_fields: false,
    attributes: [
      { key: "ref", label: "REF", type: "text", required: true, in_spec: true, options: [], unit: "", help: "", example: "71933215", column: false },
      { key: "sterile", label: "Sterile", type: "boolean", required: false, in_spec: false, options: [], unit: "", help: "", example: "", column: false },
      { key: "device_class", label: "Class", type: "choice", required: false, in_spec: false, options: ["I", "IIa", "IIb", "III"], unit: "", help: "", example: "", column: false },
    ],
  },
  terms: { item: "device", items: "devices", partner: "hospital", partners: "hospitals", site: "location", sites: "locations" },
  currency: "AUD", timezone: "Australia/Sydney",
};

describe("ProductFormModal", () => {
  it("shows the tyre size fields when there is no configuration (tyres pack)", () => {
    render(<ProductFormModal product="new" onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByLabelText(/Width \(mm\)/)).toBeTruthy();
    expect(screen.getByLabelText(/Speed rating/)).toBeTruthy();
  });

  it("shows the pack's fields and sends them as attributes", async () => {
    const fetch = vi.fn(async () => reply({ id: 9, sku: "MED-1" }, 201));
    vi.stubGlobal("fetch", fetch);
    const saved = vi.fn();
    render(<StaticConfigProvider config={medical}><ProductFormModal product="new" onClose={() => {}} onSaved={saved} /></StaticConfigProvider>);
    expect(screen.queryByLabelText(/Width/)).toBeNull();
    fireEvent.change(screen.getByLabelText(/^SKU/), { target: { value: "MED-1" } });
    fireEvent.change(screen.getByLabelText(/^Manufacturer/), { target: { value: "Orthex" } });
    fireEvent.change(screen.getByLabelText(/^Device/), { target: { value: "Cortical screw" } });
    fireEvent.change(screen.getByLabelText(/^REF/), { target: { value: "71933215" } });
    fireEvent.change(screen.getByLabelText(/^Sterile/), { target: { value: "Y" } });
    fireEvent.click(screen.getByRole("button", { name: "Save product" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    const [url, init] = fetch.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toContain("/api/products");
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({ sku: "MED-1", brand: "Orthex", pattern: "Cortical screw", attributes: { ref: "71933215", sterile: "Y" } });
    expect(body).not.toHaveProperty("width");
    expect(body.attributes).not.toHaveProperty("device_class");
  });
});
