import type { MetadataRoute } from "next";

import { listAllProducts, listCategories } from "@/lib/api/catalog";
import type { Category, Product } from "@/lib/api/types";
import { absoluteUrl } from "@/lib/seo";

export const revalidate = 3600;

const XML_ENTITIES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&apos;",
};

// Next.js writes these strings into the XML verbatim, and an image URL carrying a raw "&"
// makes the whole sitemap unparseable.
function escapeUrl(url: string): string {
  return url.replace(/[&<>"']/g, (char) => XML_ENTITIES[char]);
}

function loc(path: string): string {
  return escapeUrl(absoluteUrl(path));
}

const PAGES: MetadataRoute.Sitemap = [
  { url: loc("/"), changeFrequency: "weekly", priority: 1 },
  { url: loc("/catalog"), changeFrequency: "daily", priority: 0.9 },
  { url: loc("/about"), changeFrequency: "monthly", priority: 0.5 },
  { url: loc("/makers"), changeFrequency: "monthly", priority: 0.5 },
  { url: loc("/shipping"), changeFrequency: "yearly", priority: 0.3 },
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
      url: loc(`/catalog?category=${category.slug}`),
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
    ...products.map((product) => ({
      url: loc(`/products/${product.id}`),
      changeFrequency: "weekly" as const,
      priority: 0.7,
      images: product.image_url ? [escapeUrl(product.image_url)] : undefined,
    })),
  ];
}
