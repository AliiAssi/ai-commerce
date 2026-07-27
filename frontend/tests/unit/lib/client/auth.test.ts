import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * These guard the actual defect: not "can the store refresh" but "does logging in refresh
 * it". The session lives in an httpOnly cookie, so nothing client-side notices it changing —
 * if an auth call ever stops re-reading /api/session, the header silently goes stale again
 * until a full reload, which is exactly the bug this replaced.
 */

async function freshAuth() {
  vi.resetModules();
  return import("@/lib/client/auth");
}

const USER = { id: 7, email: "shopper@it.test", role: "customer", created_at: "2026-01-01" };

/** Routes each URL to a canned response and records the call order. */
function mockRoutes(overrides: Record<string, { ok: boolean; body: unknown }> = {}) {
  const calls: string[] = [];
  // both params are declared so mock.calls is typed as [url, init] for the assertions below
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(url);
    void init;
    const override = overrides[url];
    if (override) return { ok: override.ok, json: async () => override.body };
    if (url === "/api/session") {
      return { ok: true, json: async () => ({ user: USER, cartQuantity: 0 }) };
    }
    return { ok: true, json: async () => ({ user: USER }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("login", () => {
  it("posts to the BFF and then re-reads the session", async () => {
    const auth = await freshAuth();
    const { calls } = mockRoutes();

    const result = await auth.login("shopper@it.test", "Password#123");

    expect(result.ok).toBe(true);
    expect(calls).toEqual(["/api/auth/login", "/api/session"]);
  });

  it("sends the credentials as JSON", async () => {
    const auth = await freshAuth();
    const { fetchMock } = mockRoutes();

    await auth.login("a@b.test", "secret");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "a@b.test", password: "secret" });
  });

  it("surfaces the API's message and does NOT refresh the session on failure", async () => {
    const auth = await freshAuth();
    const { calls } = mockRoutes({
      "/api/auth/login": {
        ok: false,
        body: { error: { code: "unauthorized", message: "Invalid email or password" } },
      },
    });

    const result = await auth.login("a@b.test", "wrong");

    expect(result).toEqual({ ok: false, error: "Invalid email or password" });
    expect(calls).toEqual(["/api/auth/login"]); // no pointless re-read
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    const auth = await freshAuth();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        json: async () => {
          throw new Error("not json");
        },
      })),
    );

    const result = await auth.login("a@b.test", "x");
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/went wrong/i);
  });

  it("reports a network failure instead of throwing", async () => {
    const auth = await freshAuth();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const result = await auth.login("a@b.test", "x");
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/connection/i);
  });
});

describe("register", () => {
  it("posts to the register route and then re-reads the session", async () => {
    const auth = await freshAuth();
    const { calls } = mockRoutes();

    const result = await auth.register("new@b.test", "Password#123");

    expect(result.ok).toBe(true);
    expect(calls).toEqual(["/api/auth/register", "/api/session"]);
  });
});

describe("logout", () => {
  it("posts to the logout route and then re-reads the session", async () => {
    const auth = await freshAuth();
    const { calls } = mockRoutes({ "/api/auth/logout": { ok: true, body: null } });

    const result = await auth.logout();

    expect(result.ok).toBe(true);
    expect(calls).toEqual(["/api/auth/logout", "/api/session"]);
  });

  it("sends no body", async () => {
    const auth = await freshAuth();
    const { fetchMock } = mockRoutes({ "/api/auth/logout": { ok: true, body: null } });

    await auth.logout();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBeUndefined();
  });
});
