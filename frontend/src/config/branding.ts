/**
 * Brand Pack (frontend). Everything a customer sees as "the brand" comes from here, so a white-label deployment
 * changes NEXT_PUBLIC_BRAND_* environment variables (and the files in public/brand and src/app/icon.svg) without
 * touching business logic, APIs or data. See docs/whitelabel/04_CUSTOMER_PLAYBOOK.md.
 *
 * Two names, on purpose:
 * - productName: the software's name (ours, or a white-label reseller's), e.g. in the tab title and on sign-in.
 * - companyName: the supplier that runs the consignment programme, e.g. "Acme Tyres will call you" or
 *   "Messages from Acme Tyres". Defaults to productName for single-brand deployments.
 *
 * Colours, type scale, radii and shadows live as design tokens in `src/app/globals.css`; the accent can be
 * overridden here (`accent`), which `src/app/layout.tsx` applies as CSS variables.
 */
const env = (value: string | undefined, fallback: string) => (value && value.trim() ? value.trim() : fallback);

const productName = env(process.env.NEXT_PUBLIC_BRAND_NAME, "ConsignGrid");

export const branding = {
  productName,
  companyName: env(process.env.NEXT_PUBLIC_BRAND_COMPANY, productName),
  /** Short descriptor shown under the logo in the app sidebar. */
  descriptor: env(process.env.NEXT_PUBLIC_BRAND_DESCRIPTOR, "Consignment Operations"),
  tagline: env(process.env.NEXT_PUBLIC_BRAND_TAGLINE,
    "Consignment inventory, replenishment and stock movement — managed in one place."),
  description: "Know what you have, where it is, what has sold, what needs replenishing and where stock can be moved next.",
  /** Wordmark logo. Keep `logoWidth`/`logoHeight` at the file's intrinsic size so its aspect ratio is preserved. */
  logoPath: env(process.env.NEXT_PUBLIC_BRAND_LOGO, "/brand/logo.svg"),
  logoWidth: Number(process.env.NEXT_PUBLIC_BRAND_LOGO_WIDTH || 960),
  logoHeight: Number(process.env.NEXT_PUBLIC_BRAND_LOGO_HEIGHT || 218),
  /** Optional support contact shown on the sign-in page. */
  supportEmail: env(process.env.NEXT_PUBLIC_BRAND_SUPPORT_EMAIL, ""),
  /**
   * Accent colours (hex). Empty = the design-system default (globals.css). `accent` is a fill that always carries
   * ink text, so pick a light, saturated colour; `accentText` must reach 4.5:1 on white.
   */
  accent: {
    fill: env(process.env.NEXT_PUBLIC_BRAND_ACCENT, ""),
    hover: env(process.env.NEXT_PUBLIC_BRAND_ACCENT_HOVER, ""),
    soft: env(process.env.NEXT_PUBLIC_BRAND_ACCENT_SOFT, ""),
    text: env(process.env.NEXT_PUBLIC_BRAND_ACCENT_TEXT, ""),
  },
} as const;

/** CSS custom properties that override the design-system accent (only the ones a deployment sets). */
export function accentStyle(accent: typeof branding.accent = branding.accent): Record<string, string> {
  const vars: Record<string, string> = {};
  const valid = (v: string) => /^#[0-9a-fA-F]{3,8}$/.test(v);
  if (valid(accent.fill)) vars["--color-brand"] = accent.fill;
  if (valid(accent.hover)) vars["--color-brand-hover"] = accent.hover;
  if (valid(accent.soft)) vars["--color-brand-soft"] = accent.soft;
  if (valid(accent.text)) vars["--color-brand-text"] = accent.text;
  return vars;
}

/** A file-name-safe version of a brand name: "Acme Tyres Ltd" → "Acme-Tyres-Ltd". */
export function fileSlug(name: string): string {
  return name.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "export";
}

/** UI-only thresholds (display hints; they never change business rules). */
export const uiConfig = {
  /** Warehouse SKUs with this many or fewer available units (but more than zero) are flagged as low stock. */
  lowStockThreshold: Number(process.env.NEXT_PUBLIC_LOW_STOCK_THRESHOLD ?? 4),
  /** Open backorders older than this many days are flagged as overdue when no expected date is set. */
  backorderOverdueDays: 14,
} as const;
