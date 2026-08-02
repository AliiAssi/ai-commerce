import { describe, expect, it } from "vitest";

import { PLACES, placeFor, placeSlug } from "@/lib/provenance";

describe("placeFor", () => {
  it("matches an origin that names the place exactly", () => {
    expect(placeFor("Beit Chabab")?.name).toBe("Beit Chabab");
  });

  it("matches through a regional qualifier", () => {
    expect(placeFor("Koura, North Lebanon")?.name).toBe("Koura, North Lebanon");
    expect(placeFor("Tripoli, North Lebanon")?.name).toBe("Tripoli");
  });

  it("matches either half of a place that covers two areas", () => {
    expect(placeFor("Bekaa Valley")?.name).toBe("Hasbaya & the Bekaa");
    expect(placeFor("Chouf")?.name).toBe("Bcharre & the Chouf");
  });

  /**
   * Half the catalog's origins have no entry. Attaching the nearest one would credit another
   * village's workshop, so these must come back empty and render without a story.
   */
  it("returns nothing for an origin we have not written about", () => {
    for (const origin of ["Akkar", "Baalbek", "Jezzine, South Lebanon", "Zouk Mikael"]) {
      expect(placeFor(origin)).toBeNull();
    }
  });

  it("does not confuse two places that share a region", () => {
    expect(placeFor("Zgharta, North Lebanon")).toBeNull();
    expect(placeFor("Tyre, South Lebanon")).toBeNull();
  });

  it("handles a missing origin", () => {
    expect(placeFor(null)).toBeNull();
    expect(placeFor("")).toBeNull();
  });
});

describe("placeSlug", () => {
  it("produces a usable anchor for every place", () => {
    expect(placeSlug("Hasbaya & the Bekaa")).toBe("hasbaya-the-bekaa");
    expect(placeSlug("Koura, North Lebanon")).toBe("koura-north-lebanon");
    for (const place of PLACES) {
      expect(placeSlug(place.name)).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
    }
  });
});
