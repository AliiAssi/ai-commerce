import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RevealOnScroll } from "@/components/behaviour/reveal-on-scroll";

/**
 * jsdom has no IntersectionObserver, so the component takes its documented fallback: reveal
 * immediately. That is the path these assert, which is enough to pin the wiring that actually
 * broke — whether newly inserted .reveal elements get handled at all.
 */

function plate() {
  const el = document.createElement("article");
  el.className = "plate reveal";
  return el;
}

beforeEach(() => {
  document.body.innerHTML = "";
  vi.stubGlobal(
    "matchMedia",
    vi
      .fn()
      .mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RevealOnScroll", () => {
  it("reveals elements present at mount", async () => {
    const el = plate();
    document.body.appendChild(el);

    render(<RevealOnScroll />);

    await waitFor(() => expect(el.classList.contains("in")).toBe(true));
  });

  /**
   * The regression this exists for.
   *
   * Sorting, paging and filtering the catalog change only the query string, so usePathname()
   * is unchanged and the old pathname-keyed effect never re-ran. Every plate rendered by that
   * navigation kept `.reveal`'s opacity: 0 — a catalog that looked empty until a hard refresh.
   */
  it("reveals elements inserted after mount, as a client-side navigation does", async () => {
    render(<RevealOnScroll />);

    const first = plate();
    document.body.appendChild(first);
    await waitFor(() => expect(first.classList.contains("in")).toBe(true));

    // a second navigation, e.g. changing the sort again
    const second = plate();
    document.body.appendChild(second);
    await waitFor(() => expect(second.classList.contains("in")).toBe(true));
  });

  it("handles a whole grid replaced at once", async () => {
    render(<RevealOnScroll />);

    const grid = document.createElement("div");
    const plates = [plate(), plate(), plate(), plate()];
    plates.forEach((p) => grid.appendChild(p));
    document.body.appendChild(grid);

    await waitFor(() => {
      expect(plates.every((p) => p.classList.contains("in"))).toBe(true);
    });
  });

  it("leaves already-revealed elements alone", async () => {
    const el = plate();
    el.classList.add("in");
    el.style.transitionDelay = "999ms"; // a sentinel the component would overwrite
    document.body.appendChild(el);

    render(<RevealOnScroll />);

    await waitFor(() => expect(document.querySelectorAll(".reveal").length).toBe(1));
    expect(el.style.transitionDelay).toBe("999ms");
  });

  it("stops observing once unmounted", async () => {
    const { unmount } = render(<RevealOnScroll />);
    unmount();

    const late = plate();
    document.body.appendChild(late);

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(late.classList.contains("in")).toBe(false);
  });
});
