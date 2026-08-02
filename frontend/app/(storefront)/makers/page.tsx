import type { Metadata } from "next";
import Link from "next/link";

import { LinkButton } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/typography";
import { PLACES, placeSlug } from "@/lib/provenance";

export const metadata: Metadata = { title: "The makers" };

export default function MakersPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-14">
        <Eyebrow tone="muted">The store</Eyebrow>
        <h1 className="mt-3 max-w-[18ch] font-serif text-title leading-tight tracking-tight">
          Nothing here was made by a brand.
        </h1>
        <p className="mt-6 max-w-[52ch] text-lg text-ink-muted">
          Every good on these shelves comes from a press, a kiln, a kitchen or a workshop we buy
          from directly. No importers, no house label, the person who made it is named on the
          jar wherever we can manage it.
        </p>
      </header>

      <div className="reveal border-t border-border">
        {PLACES.map((place) => (
          <div
            key={place.name}
            id={placeSlug(place.name)}
            className="grid scroll-mt-28 gap-1 border-b border-border py-5 sm:grid-cols-[13rem_1fr] sm:gap-6"
          >
            <h2 className="font-serif text-xl">{place.name}</h2>
            <p className="text-sm leading-relaxed text-ink-muted">{place.text}</p>
          </div>
        ))}
      </div>

      <div className="reveal mt-12 flex flex-wrap items-center gap-6">
        <LinkButton href="/catalog" size="lg">
          Browse the shelves
        </LinkButton>
        <Link
          href="/about"
          className="border-b border-border py-1 text-ink transition-colors hover:border-brand hover:text-brand"
        >
          Why we do this &rarr;
        </Link>
      </div>
    </div>
  );
}
