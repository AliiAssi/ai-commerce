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

  return (
    <form action="/catalog" method="get" className={className}>
      <label className="relative block">
        <span className="sr-only">Search the store</span>
        <span className="pointer-events-none absolute inset-y-0 start-3 grid place-items-center text-ink-faint">
          <Icon name="search" />
        </span>
        <input
          type="search"
          name="q"
          defaultValue={params.get("q") ?? ""}
          placeholder="Search the store…"
          className="w-full rounded-el border border-border bg-surface-alt py-2 pe-3 ps-9 text-sm placeholder:text-ink-faint focus:border-brand focus:outline-none"
        />
      </label>
    </form>
  );
}
