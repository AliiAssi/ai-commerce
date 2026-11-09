"use client";

import DOMPurify from "dompurify";
import { marked } from "marked";

let hooked = false;

export function isStorePath(href: string | null): href is string {
  return href !== null && /^\/(?![/\\])/.test(href);
}

function ensureHook() {
  if (hooked) return;
  hooked = true;
  // The AI service only ever emits store paths; anything else (an autolinked URL, raw HTML)
  // loses its href so it renders as plain text.
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName !== "A") return;
    if (!isStorePath(node.getAttribute("href"))) {
      node.removeAttribute("href");
      return;
    }
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener");
  });
}

export function renderMarkdown(text: string): string {
  ensureHook();
  const html = marked.parse(text, { gfm: true, breaks: true, async: false });
  return DOMPurify.sanitize(html, { FORBID_TAGS: ["img"] });
}
