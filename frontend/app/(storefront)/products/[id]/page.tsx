import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { BuyBox } from "@/components/product/buy-box";
import { ReviewComposer } from "@/components/product/review-composer";
import { Provenance } from "@/components/storefront/provenance";
import { RatingSummary } from "@/components/storefront/rating-summary";
import { RelatedProducts } from "@/components/storefront/related-products";
import { ReviewList } from "@/components/storefront/review-list";
import { ProductImage } from "@/components/ui/product-image";
import { RowListSkeleton, Skeleton } from "@/components/ui/skeleton";
import { Stars } from "@/components/ui/stars";
import { Eyebrow } from "@/components/ui/typography";
import { getProduct, listAllProductIds, listReviews } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import type { Product, Review } from "@/lib/api/types";

export const revalidate = 300;

type Props = { params: Promise<{ id: string }> };

/**
 * Prerender every product that exists at build time. Without this the route renders per
 * request, which would make each product page wait on a sleeping Render backend — the exact
 * cost ISR is here to avoid. Products added later still work: dynamicParams defaults to true,
 * so an unknown id renders on demand and is cached from then on.
 */
export async function generateStaticParams() {
  try {
    const ids = await listAllProductIds();
    return ids.map((id) => ({ id: String(id) }));
  } catch {
    // no catalog reachable at build time: fall back to rendering every product on demand
    // rather than failing the build
    return [];
  }
}

async function load(idParam: string) {
  const id = Number.parseInt(idParam, 10);
  if (!Number.isInteger(id) || id <= 0) notFound();
  try {
    return await getProduct(id);
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const product = await load(id);
  const description = product.description.slice(0, 160);
  return {
    title: product.name,
    description,
    openGraph: {
      title: product.name,
      description,
      type: "website",
      images: product.image_url ? [{ url: product.image_url, alt: product.name }] : undefined,
    },
  };
}

/**
 * Search engines read availability and rating from here rather than inferring them from the
 * markup. Every field is one we already hold, so nothing is asserted that the page does not
 * also show.
 */
function productSchema(product: Product) {
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.description,
    image: product.image_url ?? undefined,
    category: product.category_name,
    offers: {
      "@type": "Offer",
      price: product.price,
      priceCurrency: "USD",
      availability:
        product.stock > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
    },
    aggregateRating:
      product.review_count > 0
        ? {
            "@type": "AggregateRating",
            ratingValue: product.rating_avg,
            reviewCount: product.review_count,
          }
        : undefined,
  };
}

export default async function ProductPage({ params }: Props) {
  const { id } = await params;
  const product = await load(id);

  // Not awaited: the product is what the page is for, so reviews and the shelf below stream
  // in behind it rather than holding the whole route back.
  const reviews = listReviews(product.id);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(productSchema(product)) }}
      />

      <nav className="mb-8 text-sm text-ink-muted" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-brand">
          Home
        </Link>
        <span className="text-ink-faint"> / </span>
        <Link href={`/catalog?category=${product.category_slug}`} className="hover:text-brand">
          {product.category_name}
        </Link>
        <span className="text-ink-faint"> / </span>
        <span className="text-ink">{product.name}</span>
      </nav>

      <div className="grid gap-14 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
        {/* The photograph is the product on a store like this one, so it holds while the
            copy beside it scrolls. */}
        <div className="relative aspect-square overflow-hidden rounded-card border border-border bg-surface-sunk lg:sticky lg:top-24">
          <ProductImage
            src={product.image_url}
            alt={product.name}
            sizes="(min-width: 1024px) 34rem, 92vw"
            priority
          />
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <Eyebrow>
              {product.category_name}
              {product.origin ? ` \u00b7 ${product.origin}` : ""}
            </Eyebrow>
            <h1 className="font-serif text-title leading-[1.08] tracking-tight">
              {product.name}
            </h1>
            <Stars rating={product.rating_avg} count={product.review_count} />
          </div>

          <BuyBox
            productId={product.id}
            name={product.name}
            price={product.price}
            stock={product.stock}
          />

          <p className="max-w-[60ch] leading-relaxed text-ink-muted">{product.description}</p>

          <Provenance origin={product.origin} />
        </div>
      </div>

      <section className="mt-20 max-w-3xl">
        <h2 className="mb-6 font-serif text-2xl">
          Reviews <span className="text-ink-faint">({product.review_count})</span>
        </h2>
        <Suspense fallback={<ReviewsSkeleton />}>
          <Reviews reviews={reviews} />
        </Suspense>
        {/* Below the reviews, not above: contributing follows reading, and the composer only
            appears at all once the server confirms this visitor could post. */}
        <div className="mt-8">
          <ReviewComposer productId={product.id} productName={product.name} />
        </div>
      </section>

      <Suspense fallback={null}>
        <RelatedProducts
          categorySlug={product.category_slug}
          categoryName={product.category_name}
          excludeId={product.id}
        />
      </Suspense>
    </>
  );
}

async function Reviews({ reviews }: { reviews: Promise<Review[]> }) {
  const list = await reviews;
  return (
    <>
      <RatingSummary reviews={list} />
      <ReviewList reviews={list} />
    </>
  );
}

function ReviewsSkeleton() {
  return (
    <div role="status" aria-label="Loading reviews">
      <div className="mb-8 flex gap-12 border-b border-border pb-8">
        <Skeleton className="h-20 w-24" />
        <Skeleton className="h-20 flex-1" />
      </div>
      <RowListSkeleton rows={3} label="Loading reviews" />
    </div>
  );
}
