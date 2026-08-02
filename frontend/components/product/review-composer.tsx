"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { StarInput } from "./star-input";
import { Button } from "@/components/ui/button";
import { InlineNote } from "@/components/ui/inline-note";
import { Stars } from "@/components/ui/stars";
import { submitReview } from "@/lib/actions/reviews";
import type { Review, ReviewEligibility } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const MIN_TEXT = 3;
const MAX_TEXT = 2000;

export function ReviewComposer({
  productId,
  productName,
  compact = false,
}: {
  productId: number;
  productName?: string;
  /** The order-line variant: tighter, and it names the product it belongs to. */
  compact?: boolean;
}) {
  const router = useRouter();
  const [eligibility, setEligibility] = useState<ReviewEligibility | null>(null);
  const [posted, setPosted] = useState<Review | null>(null);
  const [rating, setRating] = useState(0);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let live = true;
    fetch(`/api/reviews/eligibility?product=${productId}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: ReviewEligibility | null) => {
        if (live) setEligibility(data);
      })
      .catch(() => {
        // a failed check costs the entry point, never the page
        if (live) setEligibility(null);
      });
    return () => {
      live = false;
    };
  }, [productId]);

  const mine = posted ?? eligibility?.review ?? null;

  if (mine) {
    return <PostedReview review={mine} compact={compact} productName={productName} />;
  }

  // Unknown, still loading, or refused: say why only when the reason is worth reading.
  if (!eligibility?.can_review) {
    if (compact || !eligibility) return null;
    return (
      <p className="text-sm text-ink-faint" data-testid="review-gate">
        Reviews come from verified buyers.{" "}
        {eligibility.reason === "not_authenticated" && (
          <Link href="/login" className="text-brand hover:underline">
            Log in
          </Link>
        )}
      </p>
    );
  }

  const trimmed = text.trim();
  const open = rating > 0;

  const post = () => {
    startTransition(async () => {
      const result = await submitReview(productId, rating, trimmed);
      if (result.ok) {
        setPosted(result.data);
        setError(null);
        router.refresh();
      } else {
        setError(result.error);
      }
    });
  };

  return (
    <div
      data-testid="review-composer"
      className={cn(
        "flex scroll-mt-32 flex-col gap-4",
        !compact && "rounded-card border border-border bg-surface p-6",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={cn("font-medium", compact ? "text-sm" : "font-serif text-lg")}>
          {compact && productName ? `Rate ${productName}` : "Rate this product"}
        </p>
        {!open && <span className="text-xs text-ink-faint">Verified purchase</span>}
      </div>

      <StarInput value={rating} onChange={setRating} size={compact ? "md" : "lg"} />

      {open && (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="sr-only">Your review</span>
            <textarea
              rows={compact ? 3 : 4}
              value={text}
              maxLength={MAX_TEXT}
              autoFocus={!compact}
              onChange={(event) => setText(event.target.value)}
              placeholder="What should other shoppers know?"
              className="w-full rounded-el border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
            />
            {/* Said out loud rather than left as a disabled button with no explanation. */}
            <span className="flex justify-between text-xs text-ink-faint">
              <span>
                {trimmed.length > 0 && trimmed.length < MIN_TEXT
                  ? `A few more characters (${MIN_TEXT} minimum)`
                  : "A sentence or two is plenty"}
              </span>
              <span className="tabular-nums">
                {text.length}/{MAX_TEXT}
              </span>
            </span>
          </label>

          {error && <InlineNote>{error}</InlineNote>}

          <div className="flex items-center gap-4">
            <Button
              type="button"
              size={compact ? "sm" : "md"}
              onClick={post}
              disabled={pending || trimmed.length < MIN_TEXT}
            >
              {pending ? "Posting…" : "Post review"}
            </Button>
            <button
              type="button"
              onClick={() => {
                setRating(0);
                setText("");
                setError(null);
              }}
              className="text-sm text-ink-faint hover:text-brand"
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function PostedReview({
  review,
  compact,
  productName,
}: {
  review: Review;
  compact: boolean;
  productName?: string;
}) {
  return (
    <div
      data-testid="your-review"
      className={cn(
        "flex flex-col gap-2",
        !compact && "rounded-card border border-success bg-success-subtle p-6",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={cn("font-medium", compact ? "text-sm" : "font-serif text-lg")}>
          {compact && productName ? `Your review of ${productName}` : "Your review"}
        </p>
        <Stars rating={review.rating} />
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">{review.text}</p>
    </div>
  );
}
