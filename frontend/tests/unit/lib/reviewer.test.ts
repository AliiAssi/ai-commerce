import { describe, expect, it } from "vitest";

import { reviewerName } from "@/lib/reviewer";

describe("reviewerName", () => {
  /** The product page is public and cached, so no address may survive into the markup. */
  it("never leaks the domain", () => {
    for (const email of ["demo1@store.test", "a.b@example.com", "x@y.z"]) {
      expect(reviewerName(email)).not.toContain("@");
      expect(reviewerName(email)).not.toContain(email.split("@")[1]);
    }
  });

  it("shortens a full name to a first name and an initial", () => {
    expect(reviewerName("nadia.haddad@example.com")).toBe("Nadia H.");
    expect(reviewerName("omar_khoury@example.com")).toBe("Omar K.");
  });

  it("keeps a single-word handle as it is", () => {
    expect(reviewerName("demo1@store.test")).toBe("Demo1");
  });

  it("falls back rather than rendering an empty byline", () => {
    expect(reviewerName("@store.test")).toBe("A verified buyer");
  });
});
