import Image from "next/image";
import { branding } from "@/config/branding";
import { cx } from "./ui";

/**
 * The TyreGrow wordmark. Pass a height class only (e.g. "h-7"); width follows the intrinsic
 * aspect ratio, so the logo is never stretched.
 */
export function Logo({ className, priority }: { className?: string; priority?: boolean }) {
  return (
    <Image src={branding.logoPath} alt={branding.productName} width={branding.logoWidth} height={branding.logoHeight}
      className={cx("w-auto max-w-none object-contain", className ?? "h-7")} loading={priority ? "eager" : undefined}
      fetchPriority={priority ? "high" : undefined} />
  );
}
