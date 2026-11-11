/**
 * Central branding configuration. Change the product name, logo and positioning copy here (or via
 * NEXT_PUBLIC_BRAND_* environment variables) without touching business logic, APIs or data.
 * Colours, type scale, radii and shadows live as design tokens in `src/app/globals.css`.
 */
export const branding = {
  productName: process.env.NEXT_PUBLIC_BRAND_NAME ?? "TyreGrow",
  /** Short descriptor shown under the logo in the app sidebar. */
  descriptor: process.env.NEXT_PUBLIC_BRAND_DESCRIPTOR ?? "Consignment Operations",
  tagline: process.env.NEXT_PUBLIC_BRAND_TAGLINE
    ?? "Consignment inventory, replenishment and stock movement — managed in one place.",
  description: "Know what you have, where it is, what has sold, what needs replenishing and where stock can be moved next.",
  /** Wordmark logo. Keep `logoWidth`/`logoHeight` at the file's intrinsic size so its aspect ratio is preserved. */
  logoPath: process.env.NEXT_PUBLIC_BRAND_LOGO ?? "/brand/tyregrow-logo.png",
  logoWidth: Number(process.env.NEXT_PUBLIC_BRAND_LOGO_WIDTH ?? 960),
  logoHeight: Number(process.env.NEXT_PUBLIC_BRAND_LOGO_HEIGHT ?? 218),
} as const;

/** UI-only thresholds (display hints; they never change business rules). */
export const uiConfig = {
  /** Warehouse SKUs with this many or fewer available units (but more than zero) are flagged as low stock. */
  lowStockThreshold: Number(process.env.NEXT_PUBLIC_LOW_STOCK_THRESHOLD ?? 4),
  /** Open backorders older than this many days are flagged as overdue when no expected date is set. */
  backorderOverdueDays: 14,
} as const;
