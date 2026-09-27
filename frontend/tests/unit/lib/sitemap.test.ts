import { resolveSitemap } from "next/dist/build/webpack/loaders/metadata/resolve-route-data";
import { describe, expect, it, vi } from "vitest";

import sitemap from "@/app/sitemap";
import type { Category, Product } from "@/lib/api/types";

vi.mock("@/lib/api/catalog", () => ({
  listCategories: async (): Promise<Category[]> => [
    { id: 1, name: "Soap & Skincare", slug: "soap-skincare", product_count: 1 },
  ],
  listAllProducts: async (): Promise<Partial<Product>[]> => [
    {
      id: 29,
      image_url: "https://images.unsplash.com/photo-1?auto=format&fit=crop&w=900&q=80",
    },
  ],
}));

describe("sitemap.xml", () => {
  it("is well-formed XML even when image URLs carry query strings", async () => {
    const xml = resolveSitemap(await sitemap());
    const parsed = new DOMParser().parseFromString(xml, "application/xml");

    expect(parsed.getElementsByTagName("parsererror")).toHaveLength(0);
    const images = [...parsed.getElementsByTagName("image:loc")].map(
      (node) => node.textContent,
    );
    expect(images).toEqual([
      "https://images.unsplash.com/photo-1?auto=format&fit=crop&w=900&q=80",
    ]);
  });
});
