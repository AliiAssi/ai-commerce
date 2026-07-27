"use client";

import DOMPurify from "dompurify";
import { marked } from "marked";

let hooked = false;

function ensureHook() {
  if (hooked) return;
  hooked = true;
  // Links in model output go to a new tab, and never get to reach back into this one.
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

export function renderMarkdown(text: string): string {
  ensureHook();
  const html = marked.parse(text, { gfm: true, breaks: true, async: false });
  return DOMPurify.sanitize(html);
}
