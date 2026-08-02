import { CatalogLink } from "./catalog-nav";

export type ActiveFilter = {
  name: string;
  label: string;
  /** The catalog with this one filter dropped and everything else intact. */
  href: string;
};

export function ActiveFilters({
  filters,
  clearHref,
  searchTerm,
  clearSearchHref,
}: {
  filters: ActiveFilter[];
  clearHref: string;
  /** The active `q`, shown as its own chip so it can be dropped without losing the filters. */
  searchTerm?: string;
  clearSearchHref?: string | null;
}) {
  const hasSearch = Boolean(searchTerm && clearSearchHref);
  if (filters.length === 0 && !hasSearch) return null;

  return (
    <div
      className="mb-6 flex flex-wrap items-center gap-2 text-sm"
      data-testid="active-filters"
    >
      <span className="text-ink-faint">Showing</span>
      {hasSearch && (
        <CatalogLink
          href={clearSearchHref as string}
          dir="auto"
          className="group inline-flex max-w-full items-center gap-1.5 rounded-el border border-brand bg-surface-alt px-2.5 py-1 text-ink hover:border-brand hover:text-brand"
          aria-label={`Clear the search for ${searchTerm}`}
          data-testid="active-chip-q"
        >
          <span className="truncate">&ldquo;{searchTerm}&rdquo;</span>
          <span aria-hidden="true" className="text-ink-faint group-hover:text-brand">
            &times;
          </span>
        </CatalogLink>
      )}
      {filters.map((filter) => (
        <CatalogLink
          key={filter.name}
          href={filter.href}
          className="group inline-flex items-center gap-1.5 rounded-el border border-border bg-surface-alt px-2.5 py-1 text-ink-muted hover:border-brand hover:text-brand"
          aria-label={`Remove filter: ${filter.label}`}
          data-testid={`active-chip-${filter.name}`}
        >
          <span>{filter.label}</span>
          <span aria-hidden="true" className="text-ink-faint group-hover:text-brand">
            &times;
          </span>
        </CatalogLink>
      ))}
      {filters.length > 1 && (
        <CatalogLink href={clearHref} className="text-ink-faint underline hover:text-brand">
          Clear all
        </CatalogLink>
      )}
    </div>
  );
}
