import "server-only";

import { apiFetch, CATALOG_CACHE, NO_CACHE } from "./client";
import type {
  Category,
  ProductPage,
  Product,
  Review,
  ReviewEligibility,
  SortOption,
} from "./types";

export interface ProductSearch {
  q?: string;
  category?: string;
  origin?: string;
  min_price?: string;
  max_price?: string;
  in_stock_only?: boolean;
  sort?: SortOption;
  page?: number;
  page_size?: number;
  /** Inference names to suppress. Sent comma-separated, which §9.1 accepts. */
  ignore_inferred?: readonly string[];
}

export function listProducts(params: ProductSearch = {}) {
  const { ignore_inferred, ...rest } = params;
  const searching = Boolean(params.q?.trim());

  return apiFetch<ProductPage>("/products", {
    query: {
      ...rest,
      ignore_inferred: ignore_inferred?.length ? ignore_inferred.join(",") : undefined,
    },
    // §13: a search must not be served from the 300-second catalog cache. A cached search is
    // stale *and* invisible to analytics — the second search for the same words would never
    // reach the backend, so the zero-result and language reports would undercount exactly the
    // queries worth reading. Browsing keeps the cache, and that CDN-cached HTML is what keeps
    // the storefront alive while the backend sleeps.
    //
    // §12 also forbids caching a degraded response as if it were healthy, which this satisfies
    // by construction: the degraded path only exists for searches.
    cache: searching ? NO_CACHE : CATALOG_CACHE,
  });
}

export function getProduct(id: number) {
  return apiFetch<Product>(`/products/${id}`, { cache: CATALOG_CACHE });
}

export function listCategories() {
  return apiFetch<Category[]>("/categories", { cache: CATALOG_CACHE });
}

export function listReviews(productId: number) {
  return apiFetch<Review[]>(`/products/${productId}/reviews`, { cache: CATALOG_CACHE });
}

/** Per-caller, so never cached. Answers without a token too — signed out is a reason, not a 401. */
export function getReviewEligibility(productId: number, token: string | null) {
  return apiFetch<ReviewEligibility>(`/products/${productId}/reviews/eligibility`, {
    token,
    cache: NO_CACHE,
  });
}

export function createReview(
  productId: number,
  token: string,
  body: { rating: number; text: string },
) {
  return apiFetch<Review>(`/products/${productId}/reviews`, {
    method: "POST",
    token,
    body,
    cache: NO_CACHE,
  });
}

export function listFeatured() {
  return listProducts({ sort: "rating", page_size: 8 });
}

const MAX_PAGE_SIZE = 100; // the public endpoint's own cap
const MAX_PRERENDER_PAGES = 20; // 2000 products; a guard, not a limit we expect to hit

export async function listAllProductIds(): Promise<number[]> {
  const ids: number[] = [];
  let page = 1;
  let pages = 1;

  while (page <= pages && page <= MAX_PRERENDER_PAGES) {
    const result = await listProducts({ page, page_size: MAX_PAGE_SIZE });
    ids.push(...result.items.map((product) => product.id));
    pages = result.pages;
    page += 1;
  }

  return ids;
}
