import type { Metadata } from "next";

import { QuickAdd } from "@/components/cart/add-to-bag";
import { DegradedNotice, InferredChips } from "@/components/storefront/inferred-chips";
import { SortSelect } from "@/components/storefront/sort-select";
import { Button } from "@/components/ui/button";
import { FilterLink } from "@/components/ui/links";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { Plate } from "@/components/ui/plate";
import { Eyebrow } from "@/components/ui/typography";
import { listCategories, listProducts } from "@/lib/api/catalog";
import type { SearchMetadata } from "@/lib/api/types";
import { isDefaultSort, parseSort } from "@/lib/catalog-sort";
import { copyDir, copyFor, copyLang, isFaultDegradation } from "@/lib/search-copy";

export const metadata: Metadata = { title: "Catalog" };
export const revalidate = 300;

const INFERRED_NAMES = new Set([
  "category",
  "origin",
  "min_price",
  "max_price",
  "in_stock_only",
  "sort",
]);

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/** §9.1: repeatable *and* comma-separated, with unknown names dropped rather than rejected. */
function readIgnored(value: string | string[] | undefined): string[] {
  const raw = Array.isArray(value) ? value : value ? [value] : [];
  const names = raw
    .flatMap((entry) => entry.split(","))
    .map((entry) => entry.trim())
    .filter((entry) => INFERRED_NAMES.has(entry));
  return [...new Set(names)];
}

// Every filter lives in the URL, which is what makes the whole page cacheable and the rail's
// active state impossible to desync from the grid.
function readParams(raw: RawParams) {
  const pageNumber = Number.parseInt(one(raw.page), 10);
  const q = one(raw.q).trim();
  return {
    q,
    category: one(raw.category).trim(),
    origin: one(raw.origin).trim(),
    minPrice: one(raw.min_price).trim(),
    maxPrice: one(raw.max_price).trim(),
    inStockOnly: one(raw.in_stock_only) === "true",
    // The default is conditional on the query, so the query has to be read first.
    sort: parseSort(one(raw.sort), Boolean(q)),
    ignoreInferred: readIgnored(raw.ignore_inferred),
    page: Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : 1,
  };
}

type Params = ReturnType<typeof readParams>;

/**
 * Serialise the state every link has to carry.
 *
 * §5.3 requires `q`, explicit filters, inferred overrides and sort to survive pagination,
 * sorting and category links. Anything omitted here is silently dropped from the shopper's
 * search the moment they turn a page — which is the bug this function exists to prevent.
 */
function toQuery(p: Params, omit: string[] = []): URLSearchParams {
  const entries: Array<[string, string]> = [
    ["q", p.q],
    ["category", p.category],
    ["origin", p.origin],
    ["min_price", p.minPrice],
    ["max_price", p.maxPrice],
    ["in_stock_only", p.inStockOnly ? "true" : ""],
    ["sort", isDefaultSort(p.sort, Boolean(p.q)) ? "" : p.sort],
    ["ignore_inferred", p.ignoreInferred.join(",")],
  ];
  const query = new URLSearchParams();
  for (const [key, value] of entries) {
    if (value && !omit.includes(key)) query.set(key, value);
  }
  return query;
}

function catalogHref(query: URLSearchParams): string {
  const qs = query.toString();
  return qs ? `/catalog?${qs}` : "/catalog";
}

/**
 * Which of §5.3's three empty states applies.
 *
 * The distinction is not cosmetic: "widen your filters" is useless advice when the shopper set
 * no filters, and "try different words" is misleading when the smarter search simply was not
 * running.
 */
function emptyStateFor(params: Params, search: SearchMetadata | undefined) {
  const lang = copyLang(search?.language);
  const copy = copyFor(lang);
  // Only a *fault* earns the degraded wording. With smart search merely switched off, "try
  // again shortly" would be advice that never comes true.
  if (isFaultDegradation(search)) return { lang, ...copy.degradedEmpty };

  const hasFilters =
    Boolean(params.category || params.origin || params.minPrice || params.maxPrice) ||
    params.inStockOnly ||
    Object.keys(search?.inferred_filters ?? {}).length > 0;
  return { lang, ...(hasFilters ? copy.tooNarrow : copy.noResults) };
}

export default async function CatalogPage(props: { searchParams: Promise<RawParams> }) {
  const params = readParams(await props.searchParams);
  const hasQuery = Boolean(params.q);

  const [result, categories] = await Promise.all([
    listProducts({
      q: params.q || undefined,
      category: params.category || undefined,
      origin: params.origin || undefined,
      min_price: params.minPrice || undefined,
      max_price: params.maxPrice || undefined,
      in_stock_only: params.inStockOnly || undefined,
      sort: params.sort,
      page: params.page,
      ignore_inferred: params.ignoreInferred,
    }),
    listCategories(),
  ]);

  const search = result.search;
  const lang = copyLang(search?.language);

  // A category link changes the category and nothing else — and resets to page 1, which
  // happens for free because `page` is never in `toQuery`'s output.
  const railQuery = toQuery(params, ["category"]);
  const categoryHref = (slug?: string) => {
    const query = new URLSearchParams(railQuery);
    if (slug) query.set("category", slug);
    return catalogHref(query);
  };

  // §5.2.1: suppressing an inference keeps `q` and every other parameter untouched.
  const hrefWithout = (name: string) =>
    catalogHref(toQuery({ ...params, ignoreInferred: [...params.ignoreInferred, name] }));

  const totalGoods = categories.reduce((sum, c) => sum + c.product_count, 0);

  return (
    <>
      <div className="mb-10 flex items-baseline justify-between gap-6">
        <h1 className="font-serif text-4xl tracking-tight">Catalog</h1>
        <Eyebrow tone="muted">
          {result.total} good{result.total === 1 ? "" : "s"}
        </Eyebrow>
      </div>

      <div className="grid gap-12 lg:grid-cols-[13rem_1fr] lg:items-start">
        <aside className="flex flex-col gap-8 lg:sticky lg:top-24">
          <div className="flex flex-col gap-2.5">
            <Eyebrow>Category</Eyebrow>
            <div className="flex flex-col">
              <FilterLink
                href={categoryHref()}
                name="Everything"
                count={totalGoods}
                active={!params.category}
              />
              {categories.map((category) => (
                <FilterLink
                  key={category.id}
                  href={categoryHref(category.slug)}
                  name={category.name}
                  count={category.product_count}
                  active={params.category === category.slug}
                />
              ))}
            </div>
          </div>

          {/* A plain GET form, so search works without JavaScript (§5.1). Every piece of state
              the form does not draw an input for has to ride along as a hidden field, or
              applying a price filter would silently drop the shopper's chip overrides. */}
          <form action="/catalog" method="get" className="flex flex-col gap-5">
            {params.category && <input type="hidden" name="category" value={params.category} />}
            {params.origin && <input type="hidden" name="origin" value={params.origin} />}
            {!isDefaultSort(params.sort, hasQuery) && (
              <input type="hidden" name="sort" value={params.sort} />
            )}
            {params.ignoreInferred.length > 0 && (
              <input
                type="hidden"
                name="ignore_inferred"
                value={params.ignoreInferred.join(",")}
              />
            )}

            <div className="flex flex-col gap-2.5">
              <Eyebrow>Search</Eyebrow>
              <input
                type="search"
                name="q"
                dir="auto"
                maxLength={200}
                defaultValue={params.q}
                placeholder="e.g. olive oil · زيت زيتون"
                aria-label="Search the store · ابحث في المتجر"
                className="w-full rounded-el border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
              />
            </div>

            <div className="flex flex-col gap-2.5">
              <Eyebrow>Price</Eyebrow>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  name="min_price"
                  min="0"
                  step="0.01"
                  placeholder="Min"
                  aria-label="Minimum price"
                  defaultValue={params.minPrice}
                  className="w-full min-w-0 rounded-el border border-border bg-surface px-2.5 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                />
                <span aria-hidden="true" className="text-ink-faint">
                  –
                </span>
                <input
                  type="number"
                  name="max_price"
                  min="0"
                  step="0.01"
                  placeholder="Max"
                  aria-label="Maximum price"
                  defaultValue={params.maxPrice}
                  className="w-full min-w-0 rounded-el border border-border bg-surface px-2.5 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                name="in_stock_only"
                value="true"
                defaultChecked={params.inStockOnly}
                className="rounded border-border text-brand focus:ring-brand"
              />
              In stock only
            </label>

            <div className="flex items-center gap-4">
              <Button type="submit" size="sm">
                Apply
              </Button>
              <a href="/catalog" className="text-sm text-ink-faint hover:text-brand">
                Clear
              </a>
            </div>
          </form>
        </aside>

        <div>
          <div className="mb-8 flex items-baseline justify-between gap-4 border-b border-border pb-5">
            <Eyebrow tone="muted">
              {params.category ? params.category.replaceAll("-", " ") : "Everything"}
            </Eyebrow>
            <SortSelect
              value={params.sort}
              filters={toQuery(params, ["sort"]).toString()}
              hasQuery={hasQuery}
            />
          </div>

          <InferredChips search={search} lang={lang} hrefWithout={hrefWithout} />
          {isFaultDegradation(search) && result.items.length > 0 && (
            <DegradedNotice lang={lang} />
          )}

          {result.items.length > 0 ? (
            <>
              <div className="grid grid-cols-1 gap-x-7 gap-y-10 sm:grid-cols-2 xl:grid-cols-3">
                {result.items.map((product) => (
                  <Plate
                    key={product.id}
                    product={product}
                    quickAdd={<QuickAdd productId={product.id} productName={product.name} />}
                  />
                ))}
              </div>
              <Pagination page={result.page} pages={result.pages} query={toQuery(params)} />
            </>
          ) : (
            <CatalogEmptyState params={params} search={search} />
          )}
        </div>
      </div>
    </>
  );
}

function CatalogEmptyState({
  params,
  search,
}: {
  params: Params;
  search: SearchMetadata | undefined;
}) {
  const state = emptyStateFor(params, search);
  return (
    <div dir={copyDir(state.lang)}>
      <EmptyState
        title={state.title}
        body={state.body}
        ctaLabel={copyFor(state.lang).browseEverything}
        ctaHref="/catalog"
      />
    </div>
  );
}
