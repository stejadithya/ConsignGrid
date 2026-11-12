"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setWords } from "./terms";

/** One item attribute of the Industry Pack (backend/app/core/industry.py AttributeDef). */
export interface ItemAttribute {
  key: string;
  label: string;
  type: "text" | "integer" | "number" | "boolean" | "date" | "choice";
  required: boolean;
  in_spec: boolean;
  options: string[];
  unit: string;
  help: string;
  example: string;
  /** Stored in its own product column (tyres pack only). */
  column: boolean;
}

/** Public product configuration from GET /api/config/public (Brand Pack + Industry Pack). */
export interface PublicConfig {
  brand: { product_name: string; company_name: string; support_email: string };
  industry: {
    code: string; name: string; description: string; search_example: string;
    brand_label: string; name_label: string; spec_label: string; tyre_fields: boolean; attributes: ItemAttribute[];
  };
  terms: Record<string, string>;
  currency: string;
  timezone: string;
}

const ConfigContext = createContext<PublicConfig | null>(null);

/**
 * Loads the configuration once, applies the Industry Pack words, then renders the app. If the API cannot be reached
 * the app still renders, with the default words (the sign-in page then shows the connection problem as usual).
 */
export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    fetch("/api/config/public", { credentials: "same-origin" })
      .then((r) => (r.ok ? (r.json() as Promise<PublicConfig>) : null))
      .then((c) => { if (live && c) { setWords(c.terms); setConfig(c); } })
      .catch(() => undefined)
      .finally(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, []);

  if (!ready) return <div aria-busy="true" className="min-h-screen bg-canvas" />;
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

/** How items are described in this deployment. Without configuration: the tyres pack. */
export interface ItemSchema {
  tyreFields: boolean;
  brandLabel: string;
  nameLabel: string;
  specLabel: string;
  /** Attributes stored in `product.attributes` (excludes the tyre columns). */
  attributes: ItemAttribute[];
}

export function useItemSchema(): ItemSchema {
  const industry = useContext(ConfigContext)?.industry;
  if (!industry) return { tyreFields: true, brandLabel: "Brand", nameLabel: "Pattern", specLabel: "Size", attributes: [] };
  return {
    tyreFields: industry.tyre_fields, brandLabel: industry.brand_label, nameLabel: industry.name_label,
    specLabel: industry.spec_label, attributes: industry.attributes.filter((a) => !a.column),
  };
}

/** An attribute value as people read it ("Yes", "24 months"). */
export function formatAttribute(a: ItemAttribute, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (a.type === "boolean") return value ? "Yes" : "No";
  return a.unit && (a.type === "integer" || a.type === "number") ? `${value} ${a.unit}` : String(value);
}

/** Supplies a known configuration without fetching it (tests, previews). */
export function StaticConfigProvider({ config, children }: { config: PublicConfig; children: ReactNode }) {
  setWords(config.terms);
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

/** The loaded configuration, or null when it could not be loaded (defaults apply). */
export function usePublicConfig(): PublicConfig | null {
  return useContext(ConfigContext);
}
