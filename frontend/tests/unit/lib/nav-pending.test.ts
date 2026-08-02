import { describe, expect, it } from "vitest";

import { isPendingHref, optimisticParam } from "@/lib/nav-pending";

describe("isPendingHref", () => {
  it("is false while nothing is in flight", () => {
    expect(isPendingHref(null, "/catalog?category=pantry")).toBe(false);
  });

  it("marks only the link that is actually loading", () => {
    const pending = "/catalog?category=pantry";
    expect(isPendingHref(pending, pending)).toBe(true);
    expect(isPendingHref(pending, "/catalog?category=ceramics")).toBe(false);
  });
});

describe("optimisticParam", () => {
  it("falls back to the server's value while nothing is in flight", () => {
    expect(optimisticParam(null, "pantry", "category")).toBe("pantry");
  });

  it("reads the value the URL in flight will land on", () => {
    expect(optimisticParam("/catalog?category=ceramics", "pantry", "category")).toBe(
      "ceramics",
    );
  });

  /**
   * The case href equality gets wrong: a category link drops `q`, so the pending URL never
   * equals the current one even though the category is unchanged.
   */
  it("clears the value when the pending URL drops the parameter", () => {
    expect(optimisticParam("/catalog?q=olive", "pantry", "category")).toBe("");
    expect(optimisticParam("/catalog", "pantry", "category")).toBe("");
  });

  it("is unaffected by other parameters moving around it", () => {
    const href = "/catalog?q=olive&category=pantry&sort=price_asc";
    expect(optimisticParam(href, "", "category")).toBe("pantry");
    expect(optimisticParam(href, "", "sort")).toBe("price_asc");
  });
});
