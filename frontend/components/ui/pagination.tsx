import Link from "next/link";

/**
 * Plain links, no htmx target. The catalog reads its whole state from the URL, so changing
 * the page is just a navigation and the rail can never disagree with the grid.
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
        <Link href={hrefFor(page - 1)} className={linkClass}>
          &larr; Prev
        </Link>
      )}
      <span className="text-ink-muted">
        Page {page} of {pages}
      </span>
      {page < pages && (
        <Link href={hrefFor(page + 1)} className={linkClass}>
          Next &rarr;
        </Link>
      )}
    </nav>
  );
}
