import type { Metadata } from "next";
import Link from "next/link";

import { LinkButton } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/typography";
import { STORE_NAME } from "@/lib/store";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-14">
        <Eyebrow tone="muted">The store</Eyebrow>
        <h1 className="mt-3 max-w-[16ch] font-serif text-title leading-tight tracking-tight">
          بيت means home.
        </h1>
        <p className="mt-6 text-lg text-ink-muted">
          {STORE_NAME} is a small store with one idea: everything Lebanon makes well, gathered
          onto a few shelves and sourced from the people who make it.
        </p>
      </header>

      <div className="reveal space-y-10">
        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">What we stock</h2>
          <p className="leading-relaxed text-ink-muted">
            Eight shelves, kept short on purpose: olive oil and za&apos;atar, the mouneh pantry,
            coffee and sweets, ceramics, soap, textiles, cedar woodwork, glass and copper. If a
            shelf has ten things on it, we could tell you where each one was made and by whom.
            When we can&apos;t, it doesn&apos;t go on the shelf.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">How we choose</h2>
          <p className="leading-relaxed text-ink-muted">
            We buy directly from presses, kilns, kitchens and workshops,{" "}
            <Link href="/makers" className="text-brand hover:underline">
              the makers
            </Link>
            , at prices they set. Most of what we carry is made the slow way: soap cured for
            nine months, oil pressed the day of the harvest, clay fired in the same village
            kilns it has been fired in for three centuries. The store&apos;s job is only to get
            it to your door without flattening any of that.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">A note on this storefront</h2>
          <p className="leading-relaxed text-ink-muted">
            {STORE_NAME} is a working demonstration store. Every part of it functions, the
            catalog, the bag, checkout, reviews, the assistant, but payments are simulated and
            nothing is charged or shipped. Details are on the{" "}
            <Link href="/shipping" className="text-brand hover:underline">
              shipping &amp; returns
            </Link>{" "}
            page.
          </p>
        </section>
      </div>

      <div className="reveal mt-12">
        <LinkButton href="/catalog" size="lg">
          Browse the catalog
        </LinkButton>
      </div>
    </div>
  );
}
