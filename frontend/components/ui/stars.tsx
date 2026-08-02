import type { Money } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/** rating arrives as a decimal string; count is omitted on surfaces that show it elsewhere. */
export function Stars({ rating, count }: { rating: Money | number; count?: number }) {
  const value = Number(rating);
  const filled = Math.round(value);

  return (
    <span className="inline-flex items-center gap-1 text-sm">
      {/* The glyphs are decorative; `title` alone was the only rating a screen reader could
          reach, and it is not reliably announced. */}
      <span aria-hidden="true" title={`${rating} out of 5`}>
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={cn(i < filled ? "text-star" : "text-ink-faint")}>
            &#9733;
          </span>
        ))}
      </span>
      <span className="sr-only">
        Rated {value} out of 5
        {count !== undefined && ` from ${count} review${count === 1 ? "" : "s"}`}
      </span>
      {count !== undefined && (
        <span aria-hidden="true" className="text-xs text-ink-muted">
          ({count})
        </span>
      )}
    </span>
  );
}
