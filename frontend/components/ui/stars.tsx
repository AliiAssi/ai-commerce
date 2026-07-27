import type { Money } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/** rating arrives as a decimal string; count is omitted on surfaces that show it elsewhere. */
export function Stars({ rating, count }: { rating: Money | number; count?: number }) {
  const value = Number(rating);
  const filled = Math.round(value);

  return (
    <span className="inline-flex items-center gap-1 text-sm" title={`${rating} out of 5`}>
      <span aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={cn(i < filled ? "text-star" : "text-ink-faint")}>
            &#9733;
          </span>
        ))}
      </span>
      {count !== undefined && <span className="text-xs text-ink-muted">({count})</span>}
    </span>
  );
}
