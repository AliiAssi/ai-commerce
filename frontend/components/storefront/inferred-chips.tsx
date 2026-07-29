import Link from "next/link";

import type { SearchMetadata } from "@/lib/api/types";
import { chipsFor, copyDir, copyFor, type CopyLang } from "@/lib/search-copy";

/**
 * What the parser understood, as chips the shopper can switch off (§5.2).
 *
 * Removal is **filter-only** (§5.2.1). The link keeps `q` exactly as typed and adds the
 * inference name to `ignore_inferred`; it never edits the visible query. Rewriting `q` would
 * make the search box disagree with the URL, and the recognised phrase has to keep influencing
 * ranking even once its filter is gone — dropping the Beirut filter should stop Beirut being
 * exclusive, not stop it mattering.
 *
 * Plain links, so this works without JavaScript like the rest of the catalog.
 */
export function InferredChips({
  search,
  lang,
  hrefWithout,
}: {
  search: SearchMetadata | undefined;
  lang: CopyLang;
  /** Builds the URL for the page with one more inference suppressed. */
  hrefWithout: (name: string) => string;
}) {
  const chips = chipsFor(search, lang);
  if (chips.length === 0) return null;

  const copy = copyFor(lang);

  return (
    <div
      dir={copyDir(lang)}
      className="mb-6 flex flex-wrap items-center gap-2 text-sm"
      data-testid="inferred-chips"
    >
      <span className="text-ink-faint">{copy.interpretedLabel}</span>
      {chips.map((chip) => (
        <Link
          key={chip.name}
          href={hrefWithout(chip.name)}
          // Not a <button>: this is a navigation to a different set of results, and the
          // catalog reads its whole state from the URL.
          className="group inline-flex items-center gap-1.5 rounded-el border border-border bg-surface-alt px-2.5 py-1 text-ink-muted hover:border-brand hover:text-brand"
          aria-label={copy.removeFilter(chip.label)}
          data-testid={`chip-${chip.name}`}
        >
          <span>{chip.label}</span>
          <span aria-hidden="true" className="text-ink-faint group-hover:text-brand">
            &times;
          </span>
        </Link>
      ))}
    </div>
  );
}

/**
 * The degraded notice (§5.3, §12).
 *
 * Shown only when results came back degraded *and* there are results — an empty degraded
 * search gets its own empty state instead, so the shopper is not told twice.
 *
 * §5.3 forbids claiming a semantic match when the request fell back to lexical, which is the
 * whole reason this exists; §12 forbids naming a provider, so the copy says what happened to
 * the shopper, not what broke.
 */
export function DegradedNotice({ lang }: { lang: CopyLang }) {
  const copy = copyFor(lang);
  return (
    <p
      dir={copyDir(lang)}
      role="status"
      className="mb-6 rounded-el border border-border bg-surface-alt px-3 py-2 text-sm text-ink-muted"
      data-testid="degraded-notice"
    >
      {copy.degradedNotice}
    </p>
  );
}
