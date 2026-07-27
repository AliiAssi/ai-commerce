import type { Metadata } from "next";
import Link from "next/link";

import { LinkButton } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/typography";

export const metadata: Metadata = { title: "The makers" };

// The atlas: where the shelves come from. Same printed-contents rhythm as the home page's
// category index. Data-driven here because seven near-identical blocks of markup were the
// one place the Jinja template repeated itself.
const PLACES = [
  {
    name: "Koura, North Lebanon",
    text: "Olive country. The oil is pressed within hours of picking, from groves some families have held for six generations.",
  },
  {
    name: "Hasbaya & the Bekaa",
    text: "Za'atar dried on rooftops and milled by hand; mouneh, the pantry put up in season, from farm kitchens in the valley.",
  },
  {
    name: "Tripoli",
    text: "Soap city since the Mamluks. Olive oil soap is still cut by wire and cured nine months in stacked towers before it ships.",
  },
  {
    name: "Beit Chabab",
    text: "A mountain village that has thrown terracotta from its own red clay for three hundred years. Our pitchers and pots are fired there.",
  },
  {
    name: "Sarafand, South Lebanon",
    text: "One of the last hand-blown glass workshops on the Phoenician coast, turning recycled glass into sea-green tumblers.",
  },
  {
    name: "Bcharre & the Chouf",
    text: "Cedar and walnut worked into boards, boxes and backgammon sets in small mountain ateliers.",
  },
  {
    name: "Beirut",
    text: "The roasters and confectioners, cardamom coffee ground to order, and sweets that don't survive the week.",
  },
] as const;

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
            className="grid gap-1 border-b border-border py-5 sm:grid-cols-[13rem_1fr] sm:gap-6"
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
