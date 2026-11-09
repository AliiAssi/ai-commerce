import { describe, expect, it } from "vitest";

import { isStorePath, renderMarkdown } from "@/lib/client/markdown";

function anchors(markdown: string): HTMLAnchorElement[] {
  const host = document.createElement("div");
  host.innerHTML = renderMarkdown(markdown);
  return [...host.querySelectorAll("a")];
}

describe("renderMarkdown", () => {
  it("keeps store links and opens them in a new tab", () => {
    const [link] = anchors("Try [Za'atar](/products/12?utm_source=assistant&utm_medium=chat).");

    expect(link).toHaveAttribute("href", "/products/12?utm_source=assistant&utm_medium=chat");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener");
    expect(link).toHaveTextContent("Za'atar");
  });

  it.each([
    "[phish](https://evil.example)",
    "visit https://evil.example now",
    "[proto](//evil.example/x)",
    '<a href="javascript:alert(1)">x</a>',
  ])("strips the href from anything that is not a store path: %s", (markdown) => {
    for (const link of anchors(markdown)) expect(link).not.toHaveAttribute("href");
  });

  it("never renders images from model output", () => {
    expect(renderMarkdown('![x](/img/a.png) <img src="/img/b.png">')).not.toContain("<img");
  });
});

describe("isStorePath", () => {
  it.each([
    ["/products/1", true],
    ["/catalog?q=x", true],
    ["//evil.example", false],
    ["/\\evil.example", false],
    ["https://evil.example", false],
    [null, false],
  ])("%s → %s", (href, expected) => {
    expect(isStorePath(href)).toBe(expected);
  });
});
