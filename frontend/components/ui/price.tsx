import type { Money } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const SIZES = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-lg",
  xl: "text-2xl",
} as const;

export type PriceSize = keyof typeof SIZES;

/**
 * Money arrives from the API as a decimal *string*. It is parsed only here, at the point of
 * display, so no arithmetic ever runs on a float that came from a currency value.
 */
export function Price({ value, size = "md" }: { value: Money; size?: PriceSize }) {
  return (
    <span className={cn(SIZES[size], "font-serif tabular-nums text-ink")}>
      ${Number(value).toFixed(2)}
    </span>
  );
}
