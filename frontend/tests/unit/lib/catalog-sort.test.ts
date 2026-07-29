import { describe, expect, it } from "vitest";

import { defaultSort, isDefaultSort, parseSort, sortsFor } from "@/lib/catalog-sort";

// §5.3 and §9.1 make `relevance` conditional on a query being present. Everything here is
// about that one word being offered, defaulted, and serialised only when it means something.

describe("sortsFor", () => {
  it("offers relevance only while a query is active", () => {
    expect(sortsFor(true).map((o) => o.value)).toContain("relevance");
    expect(sortsFor(false).map((o) => o.value)).not.toContain("relevance");
  });

  it("puts relevance first when it is offered, since it is also the default", () => {
    expect(sortsFor(true)[0]?.value).toBe("relevance");
  });

  it("keeps every other option in both modes", () => {
    const browsing = sortsFor(false).map((o) => o.value);
    expect(browsing).toEqual(["newest", "rating", "price_asc", "price_desc"]);
    expect(sortsFor(true).map((o) => o.value)).toEqual(["relevance", ...browsing]);
  });
});

describe("defaultSort", () => {
  it("is relevance with a query and newest without one", () => {
    expect(defaultSort(true)).toBe("relevance");
    expect(defaultSort(false)).toBe("newest");
  });
});

describe("parseSort", () => {
  it("reads a valid explicit sort in either mode", () => {
    expect(parseSort("price_asc", true)).toBe("price_asc");
    expect(parseSort("price_asc", false)).toBe("price_asc");
  });

  it("falls back to the conditional default when absent", () => {
    expect(parseSort("", true)).toBe("relevance");
    expect(parseSort("", false)).toBe("newest");
  });

  it("falls back to the conditional default when the value is nonsense", () => {
    expect(parseSort("sideways", true)).toBe("relevance");
    expect(parseSort("sideways", false)).toBe("newest");
  });

  it("accepts relevance with a query", () => {
    expect(parseSort("relevance", true)).toBe("relevance");
  });

  it("rejects relevance without a query", () => {
    // The selector never offers it there, so it can only arrive from a hand-edited or stale
    // URL. Echoing it back would put the page in a state its own controls cannot produce.
    expect(parseSort("relevance", false)).toBe("newest");
  });
});

describe("isDefaultSort", () => {
  it("recognises whichever sort is currently the default", () => {
    expect(isDefaultSort("relevance", true)).toBe(true);
    expect(isDefaultSort("newest", false)).toBe(true);
  });

  it("does not treat the other mode's default as redundant", () => {
    // Dropping `sort=newest` from a search URL would silently re-sort by relevance.
    expect(isDefaultSort("newest", true)).toBe(false);
    expect(isDefaultSort("relevance", false)).toBe(false);
  });
});
