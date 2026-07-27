import { describe, expect, it } from "vitest";

import { safeNext } from "@/lib/auth/redirect";

// Deleting the Jinja page controllers deletes the only other copy of this rule, so these
// cases are the regression net for the open-redirect guard.
describe("safeNext", () => {
  it("keeps a same-site relative path", () => {
    expect(safeNext("/cart")).toBe("/cart");
    expect(safeNext("/account/orders?page=2")).toBe("/account/orders?page=2");
  });

  it("falls back when there is no target", () => {
    expect(safeNext(null)).toBe("/");
    expect(safeNext(undefined)).toBe("/");
    expect(safeNext("")).toBe("/");
  });

  it("honours a custom fallback", () => {
    expect(safeNext(null, "/login")).toBe("/login");
  });

  it("rejects absolute URLs", () => {
    expect(safeNext("https://evil.test/steal")).toBe("/");
    expect(safeNext("http://evil.test")).toBe("/");
  });

  it("rejects protocol-relative URLs", () => {
    expect(safeNext("//evil.test")).toBe("/");
    expect(safeNext("//evil.test/path")).toBe("/");
  });

  it("rejects backslash variants browsers may normalise to protocol-relative", () => {
    expect(safeNext("/\\evil.test")).toBe("/");
    expect(safeNext("\\\\evil.test")).toBe("/");
  });

  it("rejects anything not rooted at /", () => {
    expect(safeNext("cart")).toBe("/");
    expect(safeNext("javascript:alert(1)")).toBe("/");
  });
});
