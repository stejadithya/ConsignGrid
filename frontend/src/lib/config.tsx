"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setWords } from "./terms";

/** Public product configuration from GET /api/config/public (Brand Pack + Industry Pack). */
export interface PublicConfig {
  brand: { product_name: string; company_name: string; support_email: string };
  industry: { code: string; name: string; description: string; search_example: string };
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

/** The loaded configuration, or null when it could not be loaded (defaults apply). */
export function usePublicConfig(): PublicConfig | null {
  return useContext(ConfigContext);
}
