"use client";

import { useId, useState } from "react";

import { cn } from "@/lib/cn";

const RATINGS = [1, 2, 3, 4, 5] as const;

const WORDS: Record<number, string> = {
  1: "Terrible",
  2: "Poor",
  3: "Okay",
  4: "Good",
  5: "Excellent",
};

/**
 * Radios behind the glyphs rather than buttons: arrow-key movement, focus and the
 * "one of five" announcement all come from the platform instead of being reimplemented.
 */
export function StarInput({
  value,
  onChange,
  size = "md",
}: {
  value: number;
  onChange: (rating: number) => void;
  size?: "md" | "lg";
}) {
  const name = useId();
  const [hovered, setHovered] = useState(0);
  const lit = hovered || value;

  return (
    <div className="flex items-center gap-3">
      <div
        role="radiogroup"
        aria-label="Rating"
        className={cn("flex items-center", size === "lg" ? "text-3xl" : "text-xl")}
        onMouseLeave={() => setHovered(0)}
      >
        {RATINGS.map((rating) => (
          <label
            key={rating}
            className="relative cursor-pointer px-0.5 leading-none"
            onMouseEnter={() => setHovered(rating)}
          >
            {/* Overlaid and transparent rather than sr-only: the input keeps focus and the
                platform's arrow-key handling, but is also the thing a pointer actually hits,
                instead of a one-pixel box beside the star. */}
            <input
              type="radio"
              name={name}
              value={rating}
              checked={value === rating}
              onChange={() => onChange(rating)}
              className="peer absolute inset-0 cursor-pointer opacity-0"
            />
            <span
              aria-hidden="true"
              className={cn(
                "transition-colors peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-brand",
                rating <= lit ? "text-star" : "text-ink-faint",
              )}
            >
              &#9733;
            </span>
            <span className="sr-only">
              {rating} star{rating === 1 ? "" : "s"} &mdash; {WORDS[rating]}
            </span>
          </label>
        ))}
      </div>
      {lit > 0 && <span className="text-sm text-ink-muted">{WORDS[lit]}</span>}
    </div>
  );
}
