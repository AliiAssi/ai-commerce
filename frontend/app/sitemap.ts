import type { MetadataRoute } from "next";

import { listAllProducts, listCategories } from "@/lib/api/catalog";
import type { Category, Product } from "@/lib/api/types";
import { absoluteUrl } from "@/lib/seo";

export const revalidate = 3600;

const PAGES: MetadataRoute.Sitemap = [
  { url: absoluteUrl("/"), changeFrequency: "weekly", priority: 1 },
  { url: absoluteUrl("/catalog"), changeFrequency: "daily", priority: 0.9 },
  { url: absoluteUrl("/about"), changeFrequency: "monthly", priority: 0.5 },
  { url: absoluteUrl("/makers"), changeFrequency: "monthly", priority: 0.5 },
  { url: absoluteUrl("/shipping"), changeFrequency: "yearly", priority: 0.3 },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let categories: Category[] = [];
  let products: Product[] = [];
  try {
    [categories, products] = await Promise.all([listCategories(), listAllProducts()]);
  } catch {
    // the backend is unreachable: still publish the pages that need no catalog data
  }

  return [
    ...PAGES,
    ...categories.map((category) => ({
      url: absoluteUrl(`/catalog?category=${category.slug}`),
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
    ...products.map((product) => ({
      url: absoluteUrl(`/products/${product.id}`),
      changeFrequency: "weekly" as const,
      priority: 0.7,
      images: product.image_url ? [product.image_url] : undefined,
    })),
  ];
}
