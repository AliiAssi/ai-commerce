import { describe, expect, it } from "vitest";

import type { Category, Product } from "@/lib/api/types";
import { llmsText } from "@/lib/llms";
import { absoluteUrl } from "@/lib/seo";

const shelf: Category = {
  id: 5,
  name: "Soap & Skincare",
  slug: "soap-skincare",
  product_count: 3,
};

const soap: Product = {
  id: 29,
  name: "Tripoli Olive Oil Soap",
  description: "Olive oil, water and ash. Cut by hand from the slab.",
  origin: "Tripoli, North Lebanon",
  price: "9.00",
  stock: 0,
  image_url: null,
  rating_avg: "5.00",
  review_count: 1,
  is_archived: false,
  category_id: 5,
  category_name: "Soap & Skincare",
  category_slug: "soap-skincare",
  created_at: "2026-09-27T00:00:00Z",
};

describe("llmsText", () => {
  const text = llmsText([shelf], [soap]);

  it("follows the llms.txt shape: title, summary, then linked sections", () => {
    expect(text.startsWith("# BEIT\n\n> ")).toBe(true);
    const headings = text.split("\n").filter((line) => line.startsWith("## "));
    expect(headings).toEqual(["## Pages", "## Shelves", "## Products", "## Optional"]);
  });

  it("says plainly that nothing can actually be bought", () => {
    const summary = text.split("\n").find((line) => line.startsWith("> "));
    expect(summary).toContain("demonstration store");
    expect(summary).toContain("nothing is ever charged or shipped");
  });

  it("lists each product with its facts and only the first sentence of its copy", () => {
    expect(text).toContain(
      `- [Tripoli Olive Oil Soap](${absoluteUrl("/products/29")}): $9.00, Tripoli, North Lebanon, out of stock, rated 5.0/5 by 1. Olive oil, water and ash.`,
    );
    expect(text).not.toContain("Cut by hand");
  });

  it("links shelves by their catalog filter", () => {
    expect(text).toContain(
      `- [Soap & Skincare](${absoluteUrl("/catalog?category=soap-skincare")}): 3 goods`,
    );
  });

  it("still describes the store when the catalog is unreachable", () => {
    const fallback = llmsText([], []);
    expect(fallback).toContain("## Pages");
    expect(fallback).not.toContain("## Shelves");
    expect(fallback).not.toContain("## Products");
  });
});
