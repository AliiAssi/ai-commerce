"use client";

import DOMPurify from "dompurify";
import { marked } from "marked";

// marked and DOMPurify were CDN <script> tags in the Jinja app, with a hand-rolled regex
// fallback for when the CDN failed. They are real dependencies now, so the fallback is gone —
// a bundled module cannot half-load.

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

/**
 * Render assistant markdown to sanitised HTML.
 * Sanitisation is not optional: this is model output rendered with dangerouslySetInnerHTML,
 * so DOMPurify is the only thing between a prompt-injected `<img onerror>` and the DOM.
 */
export function renderMarkdown(text: string): string {
  ensureHook();
  const html = marked.parse(text, { gfm: true, breaks: true, async: false });
  return DOMPurify.sanitize(html);
}
