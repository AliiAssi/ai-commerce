import { CatalogLink } from "@/components/storefront/catalog-nav";

/**
 * Plain links, no htmx target. The catalog reads its whole state from the URL, so changing
 * the page is just a navigation and the rail can never disagree with the grid.
 *
 * Prefetched because these two are the highest-intent links on the page, and a dynamic route
 * with no loading boundary prefetches nothing by default. Outside a catalog provider — the
 * admin tables reuse this — CatalogLink degrades to an ordinary <Link>.
 */
export function Pagination({
  page,
  pages,
  baseUrl = "/catalog",
  query,
}: {
  page: number;
  pages: number;
  baseUrl?: string;
  query?: URLSearchParams;
}) {
  if (pages <= 1) return null;

  const hrefFor = (target: number) => {
    const params = new URLSearchParams(query);
    params.set("page", String(target));
    return `${baseUrl}?${params.toString()}`;
  };

  const linkClass =
    "rounded-el border border-border bg-surface px-3 py-1.5 text-ink-muted hover:border-brand hover:text-brand";

  return (
    <nav
      className="flex items-center justify-center gap-4 pt-6 text-sm"
      aria-label="Pagination"
    >
      {page > 1 && (
        <CatalogLink href={hrefFor(page - 1)} className={linkClass} prefetch>
          &larr; Prev
        </CatalogLink>
      )}
      <span className="text-ink-muted">
        Page {page} of {pages}
      </span>
      {page < pages && (
        <CatalogLink href={hrefFor(page + 1)} className={linkClass} prefetch>
          Next &rarr;
        </CatalogLink>
      )}
    </nav>
  );
}
