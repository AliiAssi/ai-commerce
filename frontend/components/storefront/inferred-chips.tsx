import { CatalogLink } from "./catalog-nav";

import type { SearchMetadata } from "@/lib/api/types";
import { chipsFor, copyDir, copyFor, type CopyLang } from "@/lib/search-copy";

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
        <CatalogLink
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
        </CatalogLink>
      ))}
    </div>
  );
}

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
