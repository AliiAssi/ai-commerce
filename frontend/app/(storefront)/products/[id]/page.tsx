import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AddToBagForm } from "@/components/cart/add-to-bag";
import { ReviewForm } from "@/components/product/review-form";
import { ReviewList } from "@/components/storefront/review-list";
import { Price } from "@/components/ui/price";
import { ProductImage } from "@/components/ui/product-image";
import { Stars } from "@/components/ui/stars";
import { Eyebrow } from "@/components/ui/typography";
import { getProduct, listAllProductIds, listReviews } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { LOW_STOCK_AT } from "@/components/ui/badge";

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
  return {
    title: product.name,
    description: product.description.slice(0, 160),
  };
}

export default async function ProductPage({ params }: Props) {
  const { id } = await params;
  const product = await load(id);
  const reviews = await listReviews(product.id);

  return (
    <>
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
        <div className="overflow-hidden rounded-card border border-border bg-surface-sunk">
          <ProductImage
            src={product.image_url}
            alt={product.name}
            className="aspect-square w-full object-cover"
          />
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <Eyebrow>
              {product.category_name}
              {product.origin ? ` · ${product.origin}` : ""}
            </Eyebrow>
            <h1 className="font-serif text-title leading-[1.08] tracking-tight">
              {product.name}
            </h1>
            <Stars rating={product.rating_avg} count={product.review_count} />
          </div>

          <Price value={product.price} size="xl" />
          <p className="max-w-[60ch] leading-relaxed text-ink-muted">{product.description}</p>

          {product.stock > 0 ? (
            <div className="flex flex-col gap-2">
              <AddToBagForm productId={product.id} stock={product.stock} />
              {product.stock <= LOW_STOCK_AT && <Eyebrow>Only {product.stock} left</Eyebrow>}
            </div>
          ) : (
            <p className="text-sm text-danger">Sold out — check back soon.</p>
          )}

          {product.origin && (
            <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-3 border-t border-border pt-5 text-sm">
              <dt className="text-ink-faint">Origin</dt>
              <dd className="m-0">{product.origin}</dd>
              <dt className="text-ink-faint">Category</dt>
              <dd className="m-0">{product.category_name}</dd>
            </dl>
          )}
        </div>
      </div>

      <section className="mt-20 max-w-3xl">
        <h2 className="mb-6 font-serif text-2xl">
          Reviews <span className="text-ink-faint">({product.review_count})</span>
        </h2>
        <ReviewList reviews={reviews} />
        <div className="mt-8">
          {/* The form decides for itself whether to show fields or a log-in prompt, because
              only the client knows who is signed in on this statically rendered page. */}
          <ReviewForm productId={product.id} />
        </div>
      </section>
    </>
  );
}
