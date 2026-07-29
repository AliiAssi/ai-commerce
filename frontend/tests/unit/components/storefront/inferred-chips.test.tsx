import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DegradedNotice, InferredChips } from "@/components/storefront/inferred-chips";
import type { SearchMetadata } from "@/lib/api/types";

function metadata(overrides: Partial<SearchMetadata> = {}): SearchMetadata {
  return {
    query: "housewarming gift from Beirut under $30",
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

/** Mirrors the catalog page: keeps `q` and adds one name to ignore_inferred. */
function hrefWithout(name: string) {
  const params = new URLSearchParams({
    q: "housewarming gift from Beirut under $30",
    ignore_inferred: name,
  });
  return `/catalog?${params.toString()}`;
}

describe("InferredChips", () => {
  it("renders nothing when the parser inferred nothing", () => {
    render(<InferredChips search={metadata()} lang="en" hrefWithout={hrefWithout} />);

    expect(screen.queryByTestId("inferred-chips")).not.toBeInTheDocument();
  });

  it("renders nothing when there is no search metadata at all", () => {
    render(<InferredChips search={undefined} lang="en" hrefWithout={hrefWithout} />);

    expect(screen.queryByTestId("inferred-chips")).not.toBeInTheDocument();
  });

  it("shows a chip per inferred filter", () => {
    render(
      <InferredChips
        search={metadata({ inferred_filters: { origin: "Beirut", max_price: "30" } })}
        lang="en"
        hrefWithout={hrefWithout}
      />,
    );

    expect(screen.getByText("From Beirut")).toBeInTheDocument();
    expect(screen.getByText("Under $30")).toBeInTheDocument();
  });

  it("keeps the original query in the removal link", () => {
    // §5.2.1: removing a chip must never edit the visible query, or the URL would contradict
    // the search box.
    render(
      <InferredChips
        search={metadata({ inferred_filters: { origin: "Beirut" } })}
        lang="en"
        hrefWithout={hrefWithout}
      />,
    );

    const href = screen.getByTestId("chip-origin").getAttribute("href") ?? "";
    const params = new URLSearchParams(href.split("?")[1]);

    expect(params.get("q")).toBe("housewarming gift from Beirut under $30");
    expect(params.get("ignore_inferred")).toBe("origin");
  });

  it("is a link, so removal works without JavaScript", () => {
    render(
      <InferredChips
        search={metadata({ inferred_filters: { origin: "Beirut" } })}
        lang="en"
        hrefWithout={hrefWithout}
      />,
    );

    expect(screen.getByTestId("chip-origin").tagName).toBe("A");
  });

  it("gives each chip an accessible name that says what removing it does", () => {
    render(
      <InferredChips
        search={metadata({ inferred_filters: { max_price: "30" } })}
        lang="en"
        hrefWithout={hrefWithout}
      />,
    );

    expect(screen.getByLabelText("Remove filter: Under $30")).toBeInTheDocument();
  });

  it("renders Arabic chips right-to-left", () => {
    render(
      <InferredChips
        search={metadata({ language: "ar", inferred_filters: { origin: "Beirut" } })}
        lang="ar"
        hrefWithout={hrefWithout}
      />,
    );

    expect(screen.getByTestId("inferred-chips")).toHaveAttribute("dir", "rtl");
    expect(screen.getByText("من Beirut")).toBeInTheDocument();
  });
});

describe("DegradedNotice", () => {
  it("tells the shopper the results are simpler, without naming anything internal", () => {
    // §5.3 forbids claiming a semantic match after a lexical fallback; §12 forbids exposing
    // providers or internals.
    render(<DegradedNotice lang="en" />);
    const text = screen.getByTestId("degraded-notice").textContent?.toLowerCase() ?? "";

    expect(text).toContain("keyword");
    for (const leak of ["ollama", "pgvector", "embedding", "vector", "api"]) {
      expect(text).not.toContain(leak);
    }
  });

  it("is announced to assistive technology", () => {
    render(<DegradedNotice lang="en" />);

    expect(screen.getByTestId("degraded-notice")).toHaveAttribute("role", "status");
  });

  it("renders in Arabic right-to-left", () => {
    render(<DegradedNotice lang="ar" />);

    expect(screen.getByTestId("degraded-notice")).toHaveAttribute("dir", "rtl");
  });
});
