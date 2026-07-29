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
        <span className="pointer-events-none absolute inset-y-0 start-3 grid place-items-center text-ink-faint">
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
          className="w-full rounded-el border border-border bg-surface-alt py-2 pe-3 ps-9 text-sm placeholder:text-ink-faint focus:border-brand focus:outline-none"
        />
      </label>
    </form>
  );
}
