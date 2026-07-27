"use client";

import { useEffect } from "react";

const STAGGER_MS = 55;
const MAX_STAGGER_STEPS = 8;

export function RevealOnScroll() {
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const canObserve = typeof IntersectionObserver !== "undefined";

    const show = (el: HTMLElement) => {
      const siblings = Array.from(el.parentElement?.children ?? []);
      const index = Math.min(Math.max(siblings.indexOf(el), 0), MAX_STAGGER_STEPS);
      el.style.transitionDelay = `${index * STAGGER_MS}ms`;
      el.classList.add("in");
    };

    if (reduced || !canObserve) {
      const revealAll = () =>
        document.querySelectorAll<HTMLElement>(".reveal:not(.in)").forEach((el) => {
          el.classList.add("in");
        });
      revealAll();
      const mutations = new MutationObserver(revealAll);
      mutations.observe(document.body, { childList: true, subtree: true });
      return () => mutations.disconnect();
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          show(entry.target as HTMLElement);
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );

    // observing the same element twice is a no-op, so re-scanning is safe
    const scan = () =>
      document
        .querySelectorAll<HTMLElement>(".reveal:not(.in)")
        .forEach((el) => observer.observe(el));

    scan();

    // Coalesced to one scan per frame: a single navigation replaces many nodes at once, and
    // only childList is watched, so adding the `in` class cannot retrigger this.
    let queued = 0;
    const mutations = new MutationObserver(() => {
      if (queued) return;
      queued = requestAnimationFrame(() => {
        queued = 0;
        scan();
      });
    });
    mutations.observe(document.body, { childList: true, subtree: true });

    return () => {
      if (queued) cancelAnimationFrame(queued);
      mutations.disconnect();
      observer.disconnect();
    };
  }, []);

  return null;
}
