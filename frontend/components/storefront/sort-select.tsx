"use client";

import { useRouter } from "next/navigation";

import type { SortOption } from "@/lib/api/types";
import { SORTS } from "@/lib/catalog-sort";

export function SortSelect({
  value,
  filters,
}: {
  value: SortOption;
  /** the active filters, already serialised, without `sort` or `page` */
  filters: string;
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
        // newest is the default, so it stays out of the URL
        if (next !== "newest") params.set("sort", next);
        const query = params.toString();
        router.push(query ? `/catalog?${query}` : "/catalog");
      }}
      className="cursor-pointer border-0 border-b border-border bg-transparent py-1 text-sm text-ink focus:outline-none"
    >
      {SORTS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.text}
        </option>
      ))}
    </select>
  );
}
