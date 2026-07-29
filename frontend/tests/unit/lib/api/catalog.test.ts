import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listProducts } from "@/lib/api/catalog";

type FetchMock = ReturnType<typeof vi.fn>;

let fetchMock: FetchMock;

const EMPTY_PAGE = { items: [], total: 0, page: 1, page_size: 12, pages: 0 };

beforeEach(() => {
  fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(EMPTY_PAGE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [
    string,
    RequestInit & { next?: { revalidate?: number } },
  ];
  return { url: new URL(url), init };
}

describe("catalog caching", () => {
  it("caches an ordinary browse for 300 seconds", async () => {
    // That CDN-cached HTML is what keeps the storefront alive while the backend sleeps.
    await listProducts({ page: 2 });
    const { init } = lastCall();

    expect(init.cache).toBe("force-cache");
    expect(init.next?.revalidate).toBe(300);
  });

  it("caches a category browse", async () => {
    await listProducts({ category: "ceramics" });

    expect(lastCall().init.cache).toBe("force-cache");
  });

  it("never caches a search", async () => {
    // §13: a cached search is stale *and* invisible to analytics — the second search for the
    // same words would never reach the backend, so the zero-result and language reports would
    // undercount exactly the queries worth reading.
    await listProducts({ q: "olive oil" });

    expect(lastCall().init.cache).toBe("no-store");
  });

  it("treats a whitespace-only query as browsing", async () => {
    await listProducts({ q: "   " });

    expect(lastCall().init.cache).toBe("force-cache");
  });

  it("never caches an Arabic search either", async () => {
    await listProducts({ q: "صابون من طرابلس" });

    expect(lastCall().init.cache).toBe("no-store");
  });
});

describe("catalog query building", () => {
  it("sends the new explicit filters", async () => {
    await listProducts({
      q: "soap",
      category: "soap-skincare",
      origin: "Tripoli",
      min_price: "10",
      max_price: "30",
      in_stock_only: true,
      sort: "relevance",
    });
    const { url } = lastCall();

    expect(url.searchParams.get("origin")).toBe("Tripoli");
    expect(url.searchParams.get("in_stock_only")).toBe("true");
    expect(url.searchParams.get("sort")).toBe("relevance");
  });

  it("sends ignore_inferred comma-separated", async () => {
    // §9.1 accepts repeated or comma-separated; one parameter keeps the URL shorter.
    await listProducts({ q: "gift from Beirut", ignore_inferred: ["origin", "sort"] });

    expect(lastCall().url.searchParams.get("ignore_inferred")).toBe("origin,sort");
  });

  it("omits ignore_inferred when nothing is suppressed", async () => {
    await listProducts({ q: "gift", ignore_inferred: [] });

    expect(lastCall().url.searchParams.has("ignore_inferred")).toBe(false);
  });

  it("omits filters that are not set", async () => {
    await listProducts({ q: "gift" });
    const { url } = lastCall();

    expect(url.searchParams.has("origin")).toBe(false);
    expect(url.searchParams.has("in_stock_only")).toBe(false);
  });
});
