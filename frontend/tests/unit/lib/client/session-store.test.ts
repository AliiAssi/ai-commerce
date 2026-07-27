import { renderHook, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The store keeps module-level state and seeds itself from localStorage at import time, so
// each test needs a fresh copy of the module — and the cache set up *before* importing it.
async function freshStore() {
  vi.resetModules();
  return import("@/lib/client/session-store");
}

const CACHE_KEY = "beit_session_hint";
const USER = { id: 7, email: "shopper@it.test", role: "customer", created_at: "2026-01-01" };

function mockSession(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("useSession", () => {
  it("loads the session on first subscribe and publishes the user", async () => {
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 3 });

    const { result } = renderHook(() => store.useSession());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.user).toEqual(USER);
    expect(result.current.cartQuantity).toBe(3);
  });

  it("distinguishes signed-out from still-loading when nothing is cached", async () => {
    const store = await freshStore();
    mockSession({ user: null, cartQuantity: 0 });

    const { result } = renderHook(() => store.useSession());
    expect(result.current.loaded).toBe(false);

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.user).toBeNull();
  });

  it("reflects a login that happens after the initial load", async () => {
    const store = await freshStore();
    mockSession({ user: null, cartQuantity: 0 });

    const { result } = renderHook(() => store.useSession());
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.user).toBeNull();

    mockSession({ user: USER, cartQuantity: 1 });
    await act(async () => {
      await store.loadSession();
    });

    expect(result.current.user).toEqual(USER);
  });

  it("reflects a logout without needing a reload", async () => {
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 2 });

    const { result } = renderHook(() => store.useSession());
    await waitFor(() => expect(result.current.user).toEqual(USER));

    mockSession({ user: null, cartQuantity: 0 });
    await act(async () => {
      await store.loadSession();
    });

    expect(result.current.user).toBeNull();
  });

  it("re-fetches on every call rather than caching the first result", async () => {
    const store = await freshStore();
    const fetchMock = mockSession({ user: null, cartQuantity: 0 });

    await store.loadSession();
    await store.loadSession();
    await store.loadSession();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/session", { cache: "no-store" });
  });

  it("updates the cart badge optimistically without a request", async () => {
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 1 });

    const { result } = renderHook(() => store.useSession());
    await waitFor(() => expect(result.current.cartQuantity).toBe(1));

    act(() => store.setCartQuantity(4));
    expect(result.current.cartQuantity).toBe(4);
    expect(result.current.user).toEqual(USER);
  });
});

/**
 * The regression this block exists for.
 *
 * The storefront's pages are prerendered, so their HTML is identical for every visitor and
 * cannot contain the account menu. Without a cached hint the header waited on /api/session,
 * and a logged-in visitor watched their own menu vanish and reappear on every refresh.
 */
describe("cached session hint", () => {
  it("is already correct at hydration when a previous visit cached a user", async () => {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ user: USER, cartQuantity: 2 }));
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 2 });

    const { result } = renderHook(() => store.useSession());

    // no waitFor: this must be right on the first client render, not after a round trip
    expect(result.current.loaded).toBe(true);
    expect(result.current.user).toEqual(USER);
    expect(result.current.cartQuantity).toBe(2);
  });

  it("is written after a successful load", async () => {
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 5 });

    await store.loadSession();

    expect(JSON.parse(localStorage.getItem(CACHE_KEY)!)).toEqual({
      user: USER,
      cartQuantity: 5,
    });
  });

  it("is removed when the server says signed out", async () => {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ user: USER, cartQuantity: 2 }));
    const store = await freshStore();
    mockSession({ user: null, cartQuantity: 0 });

    await store.loadSession();

    expect(localStorage.getItem(CACHE_KEY)).toBeNull();
  });

  it("survives a failed probe rather than flashing the visitor to logged-out", async () => {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ user: USER, cartQuantity: 2 }));
    const store = await freshStore();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const { result } = renderHook(() => store.useSession());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    // one lost request is "unknown", not "signed out"
    expect(result.current.user).toEqual(USER);
  });

  it("is dropped outright by clearSessionCache, for logout", async () => {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ user: USER, cartQuantity: 2 }));
    const store = await freshStore();

    const { result } = renderHook(() => store.useSession());
    expect(result.current.user).toEqual(USER);

    act(() => store.clearSessionCache());

    expect(result.current.user).toBeNull();
    expect(localStorage.getItem(CACHE_KEY)).toBeNull();
  });

  it("ignores a corrupted entry instead of breaking the header", async () => {
    localStorage.setItem(CACHE_KEY, "{not json");
    const store = await freshStore();
    mockSession({ user: null, cartQuantity: 0 });

    const { result } = renderHook(() => store.useSession());

    expect(result.current.user).toBeNull();
    await waitFor(() => expect(result.current.loaded).toBe(true));
  });

  it("never stores the access token — only display fields", async () => {
    const store = await freshStore();
    mockSession({ user: USER, cartQuantity: 1 });

    await store.loadSession();

    const raw = localStorage.getItem(CACHE_KEY)!;
    expect(raw).not.toMatch(/token/i);
    expect(raw).not.toMatch(/password/i);
    expect(Object.keys(JSON.parse(raw))).toEqual(["user", "cartQuantity"]);
  });
});
