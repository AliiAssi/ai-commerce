import { Stars } from "@/components/ui/stars";
import { Eyebrow } from "@/components/ui/typography";
import type { Review } from "@/lib/api/types";

const BANDS = [5, 4, 3, 2, 1] as const;

/** Built from the reviews already on the page — no extra request to show the shape. */
export function RatingSummary({ reviews }: { reviews: Review[] }) {
  if (reviews.length === 0) return null;

  const counts = new Map<number, number>(BANDS.map((band) => [band, 0]));
  for (const review of reviews) {
    counts.set(review.rating, (counts.get(review.rating) ?? 0) + 1);
  }
  const average = reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length;

  return (
    <div
      className="mb-8 flex flex-col gap-6 border-b border-border pb-8 sm:flex-row sm:items-center sm:gap-12"
      data-testid="rating-summary"
    >
      <div className="flex flex-col gap-1.5">
        <span className="font-serif text-5xl leading-none tabular-nums">
          {average.toFixed(1)}
        </span>
        <Stars rating={average} />
        <Eyebrow tone="muted">
          {reviews.length} review{reviews.length === 1 ? "" : "s"}
        </Eyebrow>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        {BANDS.map((band) => {
          const count = counts.get(band) ?? 0;
          const share = Math.round((count / reviews.length) * 100);
          return (
            <div key={band} className="flex items-center gap-3 text-xs text-ink-muted">
              <span className="w-3 tabular-nums">{band}</span>
              <span aria-hidden="true" className="text-star">
                &#9733;
              </span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-el bg-surface-sunk">
                <span
                  className="block h-full rounded-el bg-star"
                  style={{ width: `${share}%` }}
                />
              </span>
              <span className="w-6 text-right tabular-nums">{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
