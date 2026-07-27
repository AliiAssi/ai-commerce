import "server-only";

import { apiFetch, CATALOG_CACHE, NO_CACHE } from "./client";
import type { Category, Page, Product, Review, SortOption } from "./types";

export interface ProductSearch {
  q?: string;
  category?: string;
  min_price?: string;
  max_price?: string;
  sort?: SortOption;
  page?: number;
  page_size?: number;
}

export function listProducts(params: ProductSearch = {}) {
  return apiFetch<Page<Product>>("/products", { query: { ...params }, cache: CATALOG_CACHE });
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
