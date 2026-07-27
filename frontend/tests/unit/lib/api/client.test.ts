import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, CATALOG_CACHE } from "@/lib/api/client";

type FetchMock = ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200) {
  return new Response(body === null ? "" : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: FetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit & { next?: unknown }];
  return { url: new URL(url), init };
}

describe("apiFetch URL building", () => {
  it("prefixes every path with /api/v1", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/products");
    expect(lastCall().url.pathname).toBe("/api/v1/products");
  });

  it("serialises query params and drops empty ones", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/products", {
      query: { q: "tent", page: 2, category: "", sort: undefined, archived: null },
    });
    const { url } = lastCall();
    expect(url.searchParams.get("q")).toBe("tent");
    expect(url.searchParams.get("page")).toBe("2");
    // an empty category must not become `category=`, which the API would treat as a filter
    expect(url.searchParams.has("category")).toBe(false);
    expect(url.searchParams.has("sort")).toBe(false);
    expect(url.searchParams.has("archived")).toBe(false);
  });
});

describe("apiFetch auth", () => {
  it("sends the token as a bearer header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/cart", { token: "abc123" });
    const headers = lastCall().init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer abc123");
  });

  it("sends no Authorization header when there is no token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/products");
    const headers = lastCall().init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});

describe("apiFetch caching", () => {
  it("defaults to no-store, because Next 16 caches nothing implicitly", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/cart", { token: "t" });
    expect(lastCall().init.cache).toBe("no-store");
  });

  it("opts into ISR when given a revalidate policy", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/products", { cache: CATALOG_CACHE });
    const { init } = lastCall();
    expect(init.cache).toBe("force-cache");
    expect(init.next).toEqual({ revalidate: 300, tags: undefined });
  });
});

describe("apiFetch error handling", () => {
  it("maps the FastAPI error envelope onto ApiError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "not_found", message: "Product not found", details: { id: 9 } } },
        404,
      ),
    );

    const error = await apiFetch("/products/9").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.code).toBe("not_found");
    expect(apiError.message).toBe("Product not found");
    expect(apiError.details).toEqual({ id: 9 });
    expect(apiError.isNotFound).toBe(true);
  });

  it("still throws ApiError when the body is not an envelope", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502</html>", { status: 502 }));
    const error = (await apiFetch("/products").catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
  });

  it("flags 401 and 403 so callers can branch without matching strings", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "not_authenticated", message: "Not authenticated" } }, 401),
    );
    const unauthorized = (await apiFetch("/cart").catch((e: unknown) => e)) as ApiError;
    expect(unauthorized.isUnauthorized).toBe(true);
    expect(unauthorized.isForbidden).toBe(false);

    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "forbidden", message: "Nope" } }, 403),
    );
    const forbidden = (await apiFetch("/admin/dashboard").catch((e: unknown) => e)) as ApiError;
    expect(forbidden.isForbidden).toBe(true);
  });

  it("returns undefined for 204 rather than trying to parse an empty body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/cart/items/1")).resolves.toBeUndefined();
  });
});
