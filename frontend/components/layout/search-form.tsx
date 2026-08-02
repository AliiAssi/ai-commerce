"use client";

import { useSearchParams } from "next/navigation";

import { Icon } from "@/components/ui/icon";

/**
 * The one search form, drawn wherever the header needs it. A plain GET to /catalog, so it
 * works without JS; useSearchParams only keeps the current query visible in the box.
 * Callers must wrap this in <Suspense> — reading search params opts a component out of
 * static prerendering otherwise.
 */
export function SearchForm({ className = "" }: { className?: string }) {
  const params = useSearchParams();
  const query = params.get("q") ?? "";

  return (
    <form action="/catalog" method="get" className={className}>
      <label className="relative block">
        {/* Bilingual per §5.1: the input accepts both languages, so its accessible name says
            so in both. The rest of the storefront stays English (§4). */}
        <span className="sr-only">Search the store · ابحث في المتجر</span>
        {/* Physical `left`, not logical `start`. The input flips to RTL on Arabic input
            (dir="auto"), and a logical offset would carry the icon across with it — into the
            corner WebKit draws the native clear button in. The header chrome around it is
            physically laid out anyway, so the magnifier stays put in both languages. */}
        <span className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-ink-faint">
          <Icon name="search" />
        </span>
        <input
          key={query}
          type="search"
          name="q"
          // A stable hook for the suite. The placeholder is bilingual copy and will keep
          // changing; selecting on it made five tests fail the first time a word moved.
          data-testid="header-search"
          // §5.1: Arabic types right-to-left and English left-to-right, decided per-value by
          // the browser. A fixed dir would render one of the two languages backwards.
          dir="auto"
          maxLength={200}
          defaultValue={query}
          placeholder="Search the store · ابحث"
          // Padding is physical for the same reason the icon is, so Arabic text keeps its
          // clearance from the magnifier instead of running underneath it. The native WebKit
          // clear button is suppressed: it is the thing that collided, it moves with the text
          // direction, and Firefox never drew it — so removing it also makes the two agree.
          className="w-full rounded-el border border-border bg-surface-alt py-2 pl-9 pr-3 text-sm placeholder:text-ink-faint focus:border-brand focus:outline-none [&::-webkit-search-cancel-button]:[-webkit-appearance:none]"
        />
      </label>
    </form>
  );
}
