import type { Metadata } from "next";
import Link from "next/link";

import { LinkButton } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/typography";

export const metadata: Metadata = { title: "Shipping & returns" };

export default function ShippingPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-14">
        <Eyebrow tone="muted">The store</Eyebrow>
        <h1 className="mt-3 max-w-[18ch] font-serif text-title leading-tight tracking-tight">
          Shipping &amp; returns
        </h1>
        <p className="mt-6 text-lg text-ink-muted">
          The short version: this is a demonstration store. Ordering works end to end, payments
          are simulated, and nothing is ever charged or shipped.
        </p>
      </header>

      <div className="reveal space-y-10">
        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">Orders &amp; payment</h2>
          <p className="leading-relaxed text-ink-muted">
            Checkout completes instantly against a simulated payment, no card details are asked
            for, and no money moves. The moment you place an order it is confirmed as{" "}
            <em>paid</em>, stock is reserved, and it appears under{" "}
            <Link href="/account/orders" className="text-brand hover:underline">
              my orders
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">Delivery</h2>
          <p className="leading-relaxed text-ink-muted">
            Orders move through the same lifecycle a real parcel would, <em>paid</em>, then{" "}
            <em>shipped</em>, then <em>delivered</em>, updated from the store&apos;s back
            office. Since the goods are illustrative, no parcel leaves Beirut; the status is the
            whole journey.
          </p>
        </section>

        <section>
          <h2 className="mb-3 font-serif text-2xl tracking-snug">
            Cancellations &amp; returns
          </h2>
          <p className="leading-relaxed text-ink-muted">
            Any order can be cancelled from{" "}
            <Link href="/account/orders" className="text-brand hover:underline">
              my orders
            </Link>{" "}
            up until the moment it ships; cancelled stock goes straight back on the shelf. Once
            an order is marked shipped it can no longer be cancelled, and since nothing physical
            arrives, there is nothing to return.
          </p>
        </section>
      </div>

      <div className="reveal mt-12">
        <LinkButton href="/catalog" size="lg">
          Back to the catalog
        </LinkButton>
      </div>
    </div>
  );
}
