"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { useSession } from "@/lib/client/session-store";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { SelectField, TextareaField } from "@/components/ui/field";
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
  const [pending, startTransition] = useTransition();
  const toast = useToast();
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
        toast("Thanks for your review", "success");
        router.refresh();
      } else {
        toast(result.error, "danger");
      }
    });
  };

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
      <div className="flex items-center gap-4">
        <Button type="button" onClick={onSubmit} disabled={pending || text.trim().length < 3}>
          {pending ? "Submitting…" : "Submit review"}
        </Button>
        <Eyebrow>Verified purchasers only</Eyebrow>
      </div>
    </div>
  );
}
