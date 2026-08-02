import type { Metadata } from "next";
import { Suspense } from "react";

import { QuickAdd } from "@/components/cart/add-to-bag";
import { ActiveFilters, type ActiveFilter } from "@/components/storefront/active-filters";
import {
  CatalogHeading,
  CatalogNavProvider,
  CategoryLink,
  StaleResults,
} from "@/components/storefront/catalog-nav";
import { DegradedNotice, InferredChips } from "@/components/storefront/inferred-chips";
import { SortSelect } from "@/components/storefront/sort-select";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { Plate } from "@/components/ui/plate";
import {
  FilterRailSkeleton,
  PLATE_GRID,
  PlateGridSkeleton,
  Skeleton,
} from "@/components/ui/skeleton";
import { Eyebrow } from "@/components/ui/typography";
import { listCategories, listProducts } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import type { Category, ProductPage, SearchMetadata } from "@/lib/api/types";
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

/**
 * §9.1's stale-bookmark rule applies to the price boxes too. The API answers a negative or
 * non-numeric bound with a 422, which reaches this server component as a thrown ApiError and
 * takes the whole page down — so an unusable bound is dropped here instead of being sent.
 * An impossible *range* survives this and is answered with an empty grid: see `isImpossibleRange`.
 */
function readPrice(value: string | string[] | undefined): string {
  const raw = one(value).trim();
  if (!raw) return "";
  const amount = Number(raw);
  return Number.isFinite(amount) && amount >= 0 ? raw : "";
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
    minPrice: readPrice(raw.min_price),
    maxPrice: readPrice(raw.max_price),
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
 * §5.3 requires `q`, explicit filters, inferred overrides and sort to survive pagination and
 * sorting. Anything omitted here is silently dropped from the shopper's search the moment they
 * turn a page — which is the bug this function exists to prevent.
 *
 * Category links are the one deliberate exception: see `clearsSearch`.
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

function clearsSearch(p: Params): Params {
  return {
    ...p,
    q: "",
    ignoreInferred: [],
    sort: parseSort(p.sort === "relevance" ? "" : p.sort, false),
  };
}

function isImpossibleRange(p: Params): boolean {
  return Boolean(p.minPrice) && Boolean(p.maxPrice) && Number(p.minPrice) > Number(p.maxPrice);
}

function emptyPage(page: number): ProductPage {
  return { items: [], total: 0, page, page_size: 12, pages: 0 };
}

/**
 * A filter combination the API refuses is a contradiction the shopper can see and undo — an
 * empty grid under their own chips, never a 500. The impossible range is caught here so the
 * request is not even made; the 422 arm covers whatever else the API decides is unusable.
 */
async function loadProducts(params: Params): Promise<ProductPage> {
  if (isImpossibleRange(params)) return emptyPage(params.page);
  try {
    return await listProducts({
      q: params.q || undefined,
      category: params.category || undefined,
      origin: params.origin || undefined,
      min_price: params.minPrice || undefined,
      max_price: params.maxPrice || undefined,
      in_stock_only: params.inStockOnly || undefined,
      sort: params.sort,
      page: params.page,
      ignore_inferred: params.ignoreInferred,
    });
  } catch (error) {
    if (error instanceof ApiError && error.isInvalidRequest) return emptyPage(params.page);
    throw error;
  }
}

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

/** The explicit filters in play, each with the URL that drops just that one. */
function describeFilters(params: Params, categories: Category[]): ActiveFilter[] {
  const without = (patch: Partial<Params>) => catalogHref(toQuery({ ...params, ...patch }));
  const chips: ActiveFilter[] = [];

  if (params.category) {
    const known = categories.find((c) => c.slug === params.category);
    chips.push({
      name: "category",
      label: known?.name ?? params.category.replaceAll("-", " "),
      href: without({ category: "" }),
    });
  }
  if (params.origin) {
    chips.push({ name: "origin", label: params.origin, href: without({ origin: "" }) });
  }
  if (params.minPrice) {
    chips.push({
      name: "min_price",
      label: `Over $${params.minPrice}`,
      href: without({ minPrice: "" }),
    });
  }
  if (params.maxPrice) {
    chips.push({
      name: "max_price",
      label: `Under $${params.maxPrice}`,
      href: without({ maxPrice: "" }),
    });
  }
  if (params.inStockOnly) {
    chips.push({
      name: "in_stock_only",
      label: "In stock",
      href: without({ inStockOnly: false }),
    });
  }
  return chips;
}

function countFilters(p: Params): number {
  return [p.category, p.origin, p.minPrice, p.maxPrice, p.inStockOnly ? "y" : ""].filter(
    Boolean,
  ).length;
}

export default async function CatalogPage(props: { searchParams: Promise<RawParams> }) {
  const params = readParams(await props.searchParams);
  const hasQuery = Boolean(params.q);

  const products = loadProducts(params);
  const categories = listCategories();

  const filterCount = countFilters(params);

  return (
    <CatalogNavProvider category={params.category}>
      <div className="mb-10 flex items-baseline justify-between gap-6">
        <h1 className="font-serif text-4xl tracking-tight">Catalog</h1>
        <Suspense fallback={<Skeleton className="h-3 w-20" />}>
          <TotalCount products={products} />
        </Suspense>
      </div>

      <div className="grid gap-12 lg:grid-cols-[13rem_1fr] lg:items-start">
        {/* CSS can hide content but cannot reveal a closed <details>, so the desktop rail is a
            second always-open copy of the same panel rather than a media query on this one. */}
        <details
          className="border-b border-border pb-5 lg:hidden"
          data-testid="filters-disclosure"
        >
          <summary className="cursor-pointer list-none text-sm font-medium text-ink marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="inline-flex items-center gap-1.5">
              Filters
              {filterCount > 0 && (
                <span className="rounded-full bg-brand px-1.5 text-xs text-surface">
                  {filterCount}
                </span>
              )}
              <span aria-hidden="true" className="text-ink-faint">
                &darr;
              </span>
            </span>
          </summary>
          <div className="mt-6 flex flex-col gap-8">
            <Suspense fallback={<FilterRailSkeleton />}>
              <CategoryRail params={params} categories={categories} />
            </Suspense>
            <FilterForm params={params} hasQuery={hasQuery} />
          </div>
        </details>

        <aside
          className="hidden flex-col gap-8 lg:sticky lg:top-24 lg:flex"
          data-testid="filters-rail"
        >
          <Suspense fallback={<FilterRailSkeleton />}>
            <CategoryRail params={params} categories={categories} />
          </Suspense>
          <FilterForm params={params} hasQuery={hasQuery} />
        </aside>

        <div>
          <div className="mb-8 flex items-baseline justify-between gap-4 border-b border-border pb-5">
            <Eyebrow tone="muted">
              <CatalogHeading category={params.category} />
            </Eyebrow>
            <SortSelect
              value={params.sort}
              filters={toQuery(params, ["sort"]).toString()}
              hasQuery={hasQuery}
            />
          </div>

          {/* The shopper's own filters stay lit while results reload — they are the optimistic
              signal. The inferred chips describe the results, so they dim with them. */}
          <Suspense fallback={null}>
            <ActiveFilterChips params={params} categories={categories} />
          </Suspense>

          <StaleResults>
            <Suspense fallback={<PlateGridSkeleton />}>
              <Results params={params} products={products} />
            </Suspense>
          </StaleResults>
        </div>
      </div>
    </CatalogNavProvider>
  );
}

async function TotalCount({ products }: { products: Promise<ProductPage> }) {
  const { total } = await products;
  return (
    <Eyebrow tone="muted">
      {total} good{total === 1 ? "" : "s"}
    </Eyebrow>
  );
}

async function CategoryRail({
  params,
  categories,
}: {
  params: Params;
  categories: Promise<Category[]>;
}) {
  const list = await categories;
  const totalGoods = list.reduce((sum, c) => sum + c.product_count, 0);

  // A category link changes the category, drops the search term, and resets to page 1 — the
  // last happens for free because `page` is never in `toQuery`'s output.
  const railQuery = toQuery(clearsSearch(params), ["category"]);
  const categoryHref = (slug?: string) => {
    const query = new URLSearchParams(railQuery);
    if (slug) query.set("category", slug);
    return catalogHref(query);
  };

  return (
    <div className="flex flex-col gap-2.5">
      <Eyebrow>Category</Eyebrow>
      <div className="flex flex-col">
        <CategoryLink href={categoryHref()} slug="" name="Everything" count={totalGoods} />
        {list.map((category) => (
          <CategoryLink
            key={category.id}
            href={categoryHref(category.slug)}
            slug={category.slug}
            name={category.name}
            count={category.product_count}
          />
        ))}
      </div>
    </div>
  );
}

async function ActiveFilterChips({
  params,
  categories,
}: {
  params: Params;
  categories: Promise<Category[]>;
}) {
  const list = await categories;
  const clearAllHref = catalogHref(
    toQuery(params, ["category", "origin", "min_price", "max_price", "in_stock_only"]),
  );
  // Clearing the term keeps the filters, which is the opposite of what a category link does —
  // between them the shopper can drop either half of a search without losing the other.
  const clearSearchHref = params.q ? catalogHref(toQuery(clearsSearch(params))) : null;

  return (
    <ActiveFilters
      filters={describeFilters(params, list)}
      clearHref={clearAllHref}
      searchTerm={params.q}
      clearSearchHref={clearSearchHref}
    />
  );
}

async function Results({
  params,
  products,
}: {
  params: Params;
  products: Promise<ProductPage>;
}) {
  const result = await products;
  const search = result.search;
  const lang = copyLang(search?.language);

  // §5.2.1: suppressing an inference keeps `q` and every other parameter untouched.
  const hrefWithout = (name: string) =>
    catalogHref(toQuery({ ...params, ignoreInferred: [...params.ignoreInferred, name] }));

  return (
    <>
      <InferredChips search={search} lang={lang} hrefWithout={hrefWithout} />
      {isFaultDegradation(search) && result.items.length > 0 && <DegradedNotice lang={lang} />}

      {result.items.length > 0 ? (
        <>
          <div className={PLATE_GRID}>
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
    </>
  );
}

function FilterForm({ params, hasQuery }: { params: Params; hasQuery: boolean }) {
  return (
    <form action="/catalog" method="get" className="flex flex-col gap-5">
      {params.category && <input type="hidden" name="category" value={params.category} />}
      {params.origin && <input type="hidden" name="origin" value={params.origin} />}
      {!isDefaultSort(params.sort, hasQuery) && (
        <input type="hidden" name="sort" value={params.sort} />
      )}
      {params.ignoreInferred.length > 0 && (
        <input type="hidden" name="ignore_inferred" value={params.ignoreInferred.join(",")} />
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
