import Link from "next/link";

import { QuickAdd } from "@/components/cart/add-to-bag";
import { LinkButton } from "@/components/ui/button";
import { IndexRow } from "@/components/ui/links";
import { Plate } from "@/components/ui/plate";
import { Eyebrow } from "@/components/ui/typography";
import { listCategories, listFeatured } from "@/lib/api/catalog";
import { aiEnabled } from "@/lib/store";

// ISR: CDN-cached HTML is served whether or not the Render backend is awake, so a cold
// backend degrades data freshness rather than blocking the page.
export const revalidate = 300;

const HERO_LINES = ["Everything Lebanon", "makes well, in", "one small store."];

export default async function HomePage() {
  const [categories, featured] = await Promise.all([listCategories(), listFeatured()]);

  return (
    <>
      {/* The thesis. بيت — "home" — set enormous and quiet behind it: the most characteristic
          thing in this store's world, and proof the layout holds Arabic script long before
          the storefront is translated. */}
      <section className="relative -mx-4 mb-16 overflow-hidden border-b border-border px-4">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-e-0 top-1/2 -translate-y-1/2 font-serif text-mark leading-none text-ink opacity-5 select-none"
        >
          بيت
        </span>
        <div className="relative py-16 md:py-24">
          <h1 className="max-w-[14ch] font-serif text-display leading-[1.02] tracking-tight">
            {HERO_LINES.map((line, i) => (
              <span key={line} className="mask">
                <span style={{ "--i": i } as React.CSSProperties}>{line}</span>
              </span>
            ))}
          </h1>
          <p className="reveal mt-7 max-w-[44ch] text-lg text-ink-muted">
            Olive oil pressed in Koura. Soap cured nine months in Tripoli. Clay thrown in Beit
            Chabab. Sourced directly from the people who make it.
          </p>
          <div className="reveal mt-10 flex flex-wrap items-center gap-6">
            <LinkButton href="/catalog" size="lg">
              Browse the catalog
            </LinkButton>
            {aiEnabled && (
              // data-chat-open is picked up by ChatWidget; keeping it an attribute rather than
              // a prop means this stays a Server Component and ships no JS of its own
              <button
                type="button"
                data-chat-open
                className="border-b border-border py-1 text-ink transition-colors hover:border-brand hover:text-brand"
              >
                Ask the assistant &rarr;
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="mb-16">
        <div className="mb-8 flex items-baseline justify-between gap-6">
          <h2 className="font-serif text-3xl tracking-snug">The shelves</h2>
          <Eyebrow tone="muted">{categories.length} categories</Eyebrow>
        </div>
        <div className="reveal border-t border-border">
          {categories.map((category, index) => (
            <IndexRow
              key={category.id}
              number={index + 1}
              name={category.name}
              count={category.product_count}
              href={`/catalog?category=${category.slug}`}
            />
          ))}
        </div>
      </section>

      <section>
        <div className="mb-8 flex items-baseline justify-between gap-6">
          <h2 className="font-serif text-3xl tracking-snug">Best rated</h2>
          <Link href="/catalog?sort=rating" className="text-sm text-brand hover:underline">
            View all &rarr;
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-x-7 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
          {featured.items.map((product) => (
            <Plate
              key={product.id}
              product={product}
              quickAdd={<QuickAdd productId={product.id} productName={product.name} />}
            />
          ))}
        </div>
      </section>
    </>
  );
}
