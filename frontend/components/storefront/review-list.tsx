import { EmptyState } from "@/components/ui/panel";
import { Stars } from "@/components/ui/stars";
import type { Review } from "@/lib/api/types";

// created_at arrives as an ISO string; the Jinja template rendered it with strftime("%b %d, %Y").
// Fixed to en-US so the server render and the client hydration cannot disagree about locale.
const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

export function ReviewList({ reviews }: { reviews: Review[] }) {
  if (reviews.length === 0) {
    return (
      <EmptyState
        title="No reviews yet"
        body="Be the first verified purchaser to review this product."
      />
    );
  }

  return (
    <ul className="space-y-4">
      {reviews.map((review) => (
        <li key={review.id} className="rounded-card border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Stars rating={review.rating} />
            <span className="text-xs text-ink-faint">
              {review.user_email} &middot; {DATE_FORMAT.format(new Date(review.created_at))}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">{review.text}</p>
        </li>
      ))}
    </ul>
  );
}
