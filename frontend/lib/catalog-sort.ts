import type { SortOption } from "@/lib/api/types";

const BASE_SORTS: ReadonlyArray<{ value: SortOption; text: string }> = [
  { value: "newest", text: "Sort · Newest" },
  { value: "rating", text: "Best rated" },
  { value: "price_asc", text: "Price, low to high" },
  { value: "price_desc", text: "Price, high to low" },
];

const RELEVANCE = { value: "relevance" as const, text: "Sort · Relevance" };

/** Sort options for a browse page — no query, so nothing to be relevant to. */
export const SORTS = BASE_SORTS;

/**
 * §5.3: `relevance` appears in the selector only when a query is active. Offering it while
 * browsing would be a control that silently means "newest", and choosing it would put a sort
 * in the URL that the backend has to reinterpret.
 */
export function sortsFor(
  hasQuery: boolean,
): ReadonlyArray<{ value: SortOption; text: string }> {
  return hasQuery ? [RELEVANCE, ...BASE_SORTS] : BASE_SORTS;
}

/** §9.1's conditional default: relevance with a query, newest without one. */
export function defaultSort(hasQuery: boolean): SortOption {
  return hasQuery ? "relevance" : "newest";
}

const BASE_VALUES = new Set<string>(BASE_SORTS.map((option) => option.value));

/**
 * Read `sort` from the URL, falling back to the conditional default.
 *
 * `relevance` is rejected without a query rather than accepted and quietly re-mapped: the
 * selector never offers it there, so it can only arrive from a hand-edited or stale URL, and
 * echoing it back would put the page in a state its own controls cannot produce.
 */
export function parseSort(value: string, hasQuery: boolean): SortOption {
  if (value === "relevance") return hasQuery ? "relevance" : "newest";
  return BASE_VALUES.has(value) ? (value as SortOption) : defaultSort(hasQuery);
}

/** True when `sort` is doing nothing the default would not do, so it stays out of the URL. */
export function isDefaultSort(sort: SortOption, hasQuery: boolean): boolean {
  return sort === defaultSort(hasQuery);
}
