"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { useSession } from "@/lib/client/session-store";
import { Button } from "@/components/ui/button";
import { SelectField, TextareaField } from "@/components/ui/field";
import { InlineNote } from "@/components/ui/inline-note";
import { Eyebrow } from "@/components/ui/typography";
import { submitReview } from "@/lib/actions/reviews";
import Link from "next/link";

const RATINGS = [
  { value: 5, text: "5 — Excellent" },
  { value: 4, text: "4 — Good" },
  { value: 3, text: "3 — Okay" },
  { value: 2, text: "2 — Poor" },
  { value: 1, text: "1 — Terrible" },
];

export function ReviewForm({ productId }: { productId: number }) {
  const { user, loaded } = useSession();
  const [rating, setRating] = useState(5);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState(false);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  // The session arrives after hydration, so stay quiet rather than flash the wrong prompt.
  if (!loaded) return null;

  if (!user) {
    return (
      <p className="text-sm text-ink-muted">
        <Link
          href={`/login?next=/products/${productId}`}
          className="text-brand hover:underline"
        >
          Log in
        </Link>{" "}
        to review this product.
      </p>
    );
  }

  const onSubmit = () => {
    startTransition(async () => {
      const result = await submitReview(productId, rating, text);
      if (result.ok) {
        setText("");
        setError(null);
        setPosted(true);
        router.refresh();
      } else {
        setError(result.error);
      }
    });
  };

  // The refreshed list below now carries the review itself, so the form stands down rather
  // than inviting a second one.
  if (posted) {
    return (
      <div className="rounded-card border border-success bg-success-subtle p-6">
        <p role="status" className="text-sm text-success">
          Thanks — your review is posted.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-card border border-border bg-surface p-6">
      <h3 className="font-serif text-lg">Write a review</h3>
      <SelectField
        name="rating"
        label="Rating"
        options={RATINGS}
        value={rating}
        onChange={(event) => setRating(Number(event.target.value))}
      />
      <TextareaField
        name="text"
        label="Your review"
        placeholder="What should other shoppers know?"
        required
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {error && <InlineNote>{error}</InlineNote>}
      <div className="flex items-center gap-4">
        <Button type="button" onClick={onSubmit} disabled={pending || text.trim().length < 3}>
          {pending ? "Submitting…" : "Submit review"}
        </Button>
        <Eyebrow>Verified purchasers only</Eyebrow>
      </div>
    </div>
  );
}
