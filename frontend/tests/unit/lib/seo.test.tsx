import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import robots from "@/app/robots";
import { JsonLd } from "@/components/seo/json-ld";
import type { Category, Product } from "@/lib/api/types";
import {
  absoluteUrl,
  breadcrumbSchema,
  categoryDescription,
  identitySchema,
  pageMetadata,
} from "@/lib/seo";

const product: Product = {
  id: 12,
  name: "Tripoli Olive Oil Soap",
  description: "Olive oil, water and ash.",
  origin: "Tripoli",
  price: "9.00",
  stock: 60,
  image_url: null,
  rating_avg: "5.00",
  review_count: 1,
  is_archived: false,
  category_id: 5,
  category_name: "Soap & Skincare",
  category_slug: "soap-skincare",
  created_at: "2026-09-27T00:00:00Z",
};

describe("pageMetadata", () => {
  it("gives each page its own canonical and a matching link preview", () => {
    const metadata = pageMetadata({ title: "About", description: "Home.", path: "/about" });
    expect(metadata.alternates?.canonical).toBe("/about");
    expect(metadata.openGraph).toMatchObject({
      title: "About · BEIT",
      description: "Home.",
      url: "/about",
      siteName: "BEIT",
    });
  });
});

describe("categoryDescription", () => {
  it("counts the goods on the shelf", () => {
    const shelf: Category = {
      id: 1,
      name: "Glass & Copper",
      slug: "glass-copper",
      product_count: 6,
    };
    expect(categoryDescription(shelf)).toContain("6 goods");
    expect(categoryDescription({ ...shelf, product_count: 1 })).toContain("1 good,");
  });
});

describe("structured data", () => {
  it("walks the breadcrumb from home through the shelf to the product", () => {
    const crumbs = breadcrumbSchema(product).itemListElement;
    expect(crumbs.map((crumb) => crumb.name)).toEqual([
      "Home",
      "Soap & Skincare",
      "Tripoli Olive Oil Soap",
    ]);
    expect(crumbs.map((crumb) => crumb.position)).toEqual([1, 2, 3]);
    expect(crumbs[2].item).toBe(absoluteUrl("/products/12"));
  });

  it("names the store and its author", () => {
    const types = identitySchema()["@graph"].map((node) => node["@type"]);
    expect(types).toEqual(["Organization", "WebSite", "Person"]);
  });

  it("cannot be broken out of by a closing script tag in the data", () => {
    const html = renderToStaticMarkup(<JsonLd data={{ name: "</script><script>alert(1)" }} />);
    expect(html).not.toContain("</script><script>");
    expect(html).toContain("\\u003c/script>");
  });
});

describe("robots.txt", () => {
  it("keeps crawlers out of private pages and points at the sitemap", () => {
    const rules = robots();
    const [rule] = Array.isArray(rules.rules) ? rules.rules : [rules.rules];
    expect(rule.disallow).toEqual(
      expect.arrayContaining(["/admin", "/api/", "/account", "/cart", "/checkout"]),
    );
    expect(rules.sitemap).toBe(absoluteUrl("/sitemap.xml"));
  });
});
