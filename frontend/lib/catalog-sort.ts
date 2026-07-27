import type { SortOption } from "@/lib/api/types";

export const SORTS: ReadonlyArray<{ value: SortOption; text: string }> = [
  { value: "newest", text: "Sort · Newest" },
  { value: "rating", text: "Best rated" },
  { value: "price_asc", text: "Price, low to high" },
  { value: "price_desc", text: "Price, high to low" },
];

const SORT_VALUES = new Set<string>(SORTS.map((option) => option.value));

export function parseSort(value: string): SortOption {
  return SORT_VALUES.has(value) ? (value as SortOption) : "newest";
}
