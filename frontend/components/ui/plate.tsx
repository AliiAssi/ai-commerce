import Link from "next/link";
import type { ReactNode } from "react";

import { Price } from "./price";
import { ProductImage } from "./product-image";
import { Stars } from "./stars";
import { Eyebrow } from "./typography";
import { LOW_STOCK_AT } from "./badge";
import type { Product } from "@/lib/api/types";

const TAG_BASE =
  "absolute left-2.5 top-2.5 rounded-el border bg-surface px-1.5 py-0.5 text-[0.625rem] uppercase tracking-label";

/**
 * Stock state, shown on the plate image itself. Silent when amply in stock — a badge on
 * every card is noise.
 */
export function PlateTag({ stock }: { stock: number }) {
  if (stock <= 0) {
    return <span className={`${TAG_BASE} border-border text-ink-faint`}>Sold out</span>;
  }
  if (stock <= LOW_STOCK_AT) {
    return <span className={`${TAG_BASE} border-clay text-clay`}>Only {stock} left</span>;
  }
  return null;
}

/**
 * A catalogue plate: the product card. Enters greyscale and resolves to full material colour
 * on intent (see .plate/.plate-art in app.css).
 *
 * `quickAdd` is a slot rather than a built-in form. Phase 2 renders plates read-only and
 * passes nothing; Phase 3 passes the add-to-bag control once cart mutations exist.
 */
export function Plate({ product, quickAdd }: { product: Product; quickAdd?: ReactNode }) {
  return (
    /* RevealOnScroll owns this element's class and transition-delay from outside React. When
       a plate arrives inside a streamed Suspense boundary — the related shelf, or the catalog
       grid on a slow backend — the observer marks it before React hydrates that subtree, and
       hydration then compares against a DOM it did not write. Declaring the element
       externally managed is the accurate description; React leaves the reveal in place. */
    <article className="plate reveal flex flex-col gap-3.5" suppressHydrationWarning>
      {/* The quick-add button is absolutely positioned, so it has to sit inside this
          relative box rather than beside the link — otherwise it anchors to whatever is
          positioned further up the tree and lands off the image entirely. Keeping it a
          sibling of the link (not a child) also stops a button nesting inside an anchor. */}
      <div className="relative aspect-[4/5] overflow-hidden rounded-card border border-border bg-surface-sunk">
        <Link
          href={`/products/${product.id}`}
          className="block h-full w-full"
          aria-label={product.name}
        >
          <ProductImage
            src={product.image_url}
            alt={product.name}
            sizes="(min-width: 1280px) 22rem, (min-width: 640px) 45vw, 90vw"
            className="plate-art"
          />
        </Link>
        <PlateTag stock={product.stock} />
        {product.stock > 0 && quickAdd}
      </div>
      <Link
        href={`/products/${product.id}`}
        className="font-serif text-lg leading-snug hover:text-brand"
      >
        {product.name}
      </Link>
      <Stars rating={product.rating_avg} count={product.review_count} />
      <div className="mt-auto flex items-baseline justify-between gap-3 pt-1">
        <Eyebrow>{product.origin ?? product.category_name}</Eyebrow>
        <Price value={product.price} size="lg" />
      </div>
    </article>
  );
}
