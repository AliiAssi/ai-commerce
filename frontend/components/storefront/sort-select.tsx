"use client";

import { useRouter } from "next/navigation";

import type { SortOption } from "@/lib/api/types";
import { isDefaultSort, sortsFor } from "@/lib/catalog-sort";

export function SortSelect({
  value,
  filters,
  hasQuery = false,
}: {
  value: SortOption;
  /** the active filters, already serialised, without `sort` or `page` */
  filters: string;
  /** §5.3: relevance is offered, and is the default, only while a query is active */
  hasQuery?: boolean;
}) {
  const router = useRouter();

  return (
    <select
      name="sort"
      aria-label="Sort products"
      value={value}
      onChange={(event) => {
        const params = new URLSearchParams(filters);
        const next = event.target.value as SortOption;
        // Whichever sort is already the default stays out of the URL — newest while browsing,
        // relevance while searching. Changing the query then changes the default with it,
        // instead of leaving a stale sort pinned in the address bar.
        if (!isDefaultSort(next, hasQuery)) params.set("sort", next);
        // §5.3: a sort change resets to page 1. `filters` already excludes `page`, so this is
        // a note about why it must keep doing so.
        const query = params.toString();
        router.push(query ? `/catalog?${query}` : "/catalog");
      }}
      className="cursor-pointer border-0 border-b border-border bg-transparent py-1 text-sm text-ink focus:outline-none"
    >
      {sortsFor(hasQuery).map((option) => (
        <option key={option.value} value={option.value}>
          {option.text}
        </option>
      ))}
    </select>
  );
}
