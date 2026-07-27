"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

// Ported from revealAll() in web/app/ui/static/js/app.js. Elements opt in with className
// "reveal"; this adds "in" when they scroll into view, staggering siblings, then stops
// observing so scrolling back up stays calm. Markup is unchanged from the Jinja templates.
const STAGGER_MS = 55;
const MAX_STAGGER_STEPS = 8;

export function RevealOnScroll() {
  const pathname = usePathname();

  useEffect(() => {
    const elements = Array.from(document.querySelectorAll<HTMLElement>(".reveal:not(.in)"));
    if (elements.length === 0) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || typeof IntersectionObserver === "undefined") {
      elements.forEach((el) => el.classList.add("in"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const el = entry.target as HTMLElement;
          const siblings = Array.from(el.parentElement?.children ?? []);
          const index = Math.min(siblings.indexOf(el), MAX_STAGGER_STEPS);
          el.style.transitionDelay = `${index * STAGGER_MS}ms`;
          el.classList.add("in");
          observer.unobserve(el);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
    // re-scan after a navigation, the way the Jinja version re-ran on htmx:afterSwap
  }, [pathname]);

  return null;
}
