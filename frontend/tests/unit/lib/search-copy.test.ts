import { describe, expect, it } from "vitest";

import type { SearchMetadata } from "@/lib/api/types";
import { chipsFor, copyDir, copyFor, copyLang, isFaultDegradation } from "@/lib/search-copy";

function metadata(overrides: Partial<SearchMetadata> = {}): SearchMetadata {
  return {
    query: "olive oil",
    language: "en",
    mode: "lexical",
    reranked: false,
    effective_sort: "relevance",
    inferred_filters: {},
    ignored_inferred: [],
    degraded: false,
    degraded_reason: null,
    ...overrides,
  };
}

describe("copyLang", () => {
  it("follows the detected query language", () => {
    expect(copyLang("ar")).toBe("ar");
    expect(copyLang("en")).toBe("en");
  });

  it("reads mixed queries as English, the storefront's own language", () => {
    expect(copyLang("mixed")).toBe("en");
  });

  it("falls back to English when there is no search metadata at all", () => {
    expect(copyLang(undefined)).toBe("en");
  });
});

describe("copyDir", () => {
  it("flips direction for Arabic copy", () => {
    expect(copyDir("ar")).toBe("rtl");
    expect(copyDir("en")).toBe("ltr");
  });
});

describe("chipsFor", () => {
  it("returns nothing when there is no search metadata", () => {
    expect(chipsFor(undefined, "en")).toEqual([]);
  });

  it("returns nothing when the parser inferred nothing", () => {
    expect(chipsFor(metadata(), "en")).toEqual([]);
  });

  it("labels each inference in English", () => {
    const chips = chipsFor(
      metadata({
        inferred_filters: {
          category: "Soap & Skincare",
          origin: "Beirut",
          max_price: "30",
          in_stock_only: "True",
        },
      }),
      "en",
    );

    expect(chips.map((c) => c.label)).toEqual([
      "Soap & Skincare",
      "From Beirut",
      "Under $30",
      "In stock",
    ]);
  });

  it("labels each inference in Arabic", () => {
    const chips = chipsFor(
      metadata({
        language: "ar",
        inferred_filters: { origin: "Tripoli", max_price: "30", in_stock_only: "True" },
      }),
      "ar",
    );

    expect(chips.map((c) => c.label)).toEqual(["من Tripoli", "تحت 30$", "متوفر"]);
  });

  it("keeps a fixed order regardless of key order in the response", () => {
    // Removing one chip must not reshuffle the others under the shopper's cursor.
    const chips = chipsFor(
      metadata({ inferred_filters: { max_price: "30", category: "Ceramics" } }),
      "en",
    );

    expect(chips.map((c) => c.name)).toEqual(["category", "max_price"]);
  });

  it("carries the inference name, which is what the removal link suppresses", () => {
    const chips = chipsFor(metadata({ inferred_filters: { origin: "Beirut" } }), "en");

    expect(chips[0]?.name).toBe("origin");
  });

  it("shows nothing for an inference the response did not report", () => {
    // §5.2.1: a suppressed inference is already absent from inferred_filters, because the
    // response must not report a filter it did not apply. No second check is needed.
    const chips = chipsFor(
      metadata({ inferred_filters: { max_price: "30" }, ignored_inferred: ["origin"] }),
      "en",
    );

    expect(chips.map((c) => c.name)).toEqual(["max_price"]);
  });

  it("renders a sort inference as a readable phrase", () => {
    const chips = chipsFor(metadata({ inferred_filters: { sort: "price_asc" } }), "en");

    expect(chips[0]?.label).toBe("Sorted by lowest price");
  });
});

describe("isFaultDegradation", () => {
  it("is false when nothing degraded", () => {
    expect(isFaultDegradation(metadata())).toBe(false);
  });

  it("is false when there is no search metadata", () => {
    expect(isFaultDegradation(undefined)).toBe(false);
  });

  it("is false when smart search is merely switched off", () => {
    // This is the state of every deploy until the embedding phases land. Telling the shopper
    // "briefly unavailable" on every search for months would be untrue, and a warning seen
    // every time is a warning nobody reads.
    expect(
      isFaultDegradation(metadata({ degraded: true, degraded_reason: "feature_disabled" })),
    ).toBe(false);
  });

  it.each([
    "search_unavailable",
    "embedding_unavailable",
    "reranker_unavailable",
    "index_incomplete",
  ] as const)("is true for %s, which is an actual fault", (reason) => {
    expect(isFaultDegradation(metadata({ degraded: true, degraded_reason: reason }))).toBe(
      true,
    );
  });
});

describe("customer-facing copy", () => {
  const PROVIDER_WORDS = [
    "ollama",
    "pgvector",
    "embedding",
    "vector",
    "rerank",
    "api",
    "token",
    "500",
    "timeout",
    "exception",
  ];

  for (const lang of ["en", "ar"] as const) {
    it(`names no provider or internal detail in ${lang}`, () => {
      // §12: customer-facing copy must not expose "Ollama", "pgvector", API keys or internal
      // exceptions. §5.3 also forbids claiming a semantic match after a lexical fallback.
      const copy = copyFor(lang);
      const text = [
        copy.interpretedLabel,
        copy.degradedNotice,
        copy.noResults.title,
        copy.noResults.body,
        copy.tooNarrow.title,
        copy.tooNarrow.body,
        copy.degradedEmpty.title,
        copy.degradedEmpty.body,
        copy.browseEverything,
      ]
        .join(" ")
        .toLowerCase();

      for (const word of PROVIDER_WORDS) {
        expect(text).not.toContain(word);
      }
    });

    it(`distinguishes all three empty states in ${lang}`, () => {
      // §5.3 requires no-relevant-products, filters-too-narrow, and degraded-and-empty to read
      // differently — the advice each one implies is different.
      const copy = copyFor(lang);
      const titles = [copy.noResults.title, copy.tooNarrow.title, copy.degradedEmpty.title];

      expect(new Set(titles).size).toBe(3);
    });
  }

  it("uses Arabic script for Arabic copy", () => {
    expect(copyFor("ar").noResults.title).toMatch(/[؀-ۿ]/);
  });
});
