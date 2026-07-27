import type { Metadata } from "next";

import { QuickAdd } from "@/components/cart/add-to-bag";
import { SortSelect } from "@/components/storefront/sort-select";
import { Button } from "@/components/ui/button";
import { FilterLink } from "@/components/ui/links";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { Plate } from "@/components/ui/plate";
import { Eyebrow } from "@/components/ui/typography";
import { listCategories, listProducts } from "@/lib/api/catalog";
import { parseSort } from "@/lib/catalog-sort";

export const metadata: Metadata = { title: "Catalog" };
export const revalidate = 300;

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

// Every filter lives in the URL, which is what makes the whole page cacheable and the rail's
// active state impossible to desync from the grid.
function readParams(raw: RawParams) {
  const pageNumber = Number.parseInt(one(raw.page), 10);
  return {
    q: one(raw.q).trim(),
    category: one(raw.category).trim(),
    minPrice: one(raw.min_price).trim(),
    maxPrice: one(raw.max_price).trim(),
    sort: parseSort(one(raw.sort)),
    page: Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : 1,
  };
}

function toQuery(p: ReturnType<typeof readParams>, omit: string[] = []): URLSearchParams {
  const entries: Array<[string, string]> = [
    ["q", p.q],
    ["category", p.category],
    ["min_price", p.minPrice],
    ["max_price", p.maxPrice],
    ["sort", p.sort === "newest" ? "" : p.sort],
  ];
  const query = new URLSearchParams();
  for (const [key, value] of entries) {
    if (value && !omit.includes(key)) query.set(key, value);
  }
  return query;
}

export default async function CatalogPage(props: { searchParams: Promise<RawParams> }) {
  const params = readParams(await props.searchParams);

  const [result, categories] = await Promise.all([
    listProducts({
      q: params.q || undefined,
      category: params.category || undefined,
      min_price: params.minPrice || undefined,
      max_price: params.maxPrice || undefined,
      sort: params.sort,
      page: params.page,
    }),
    listCategories(),
  ]);

  const railQuery = toQuery(params, ["category"]);
  const categoryHref = (slug?: string) => {
    const query = new URLSearchParams(railQuery);
    if (slug) query.set("category", slug);
    const qs = query.toString();
    return qs ? `/catalog?${qs}` : "/catalog";
  };
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

          <form action="/catalog" method="get" className="flex flex-col gap-5">
            {params.category && <input type="hidden" name="category" value={params.category} />}
            {params.sort !== "newest" && (
              <input type="hidden" name="sort" value={params.sort} />
            )}

            <div className="flex flex-col gap-2.5">
              <Eyebrow>Search</Eyebrow>
              <input
                type="search"
                name="q"
                defaultValue={params.q}
                placeholder="e.g. olive oil"
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
            <SortSelect value={params.sort} filters={toQuery(params, ["sort"]).toString()} />
          </div>

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
            <EmptyState
              title="Nothing on this shelf"
              body="Try different words, or widen the price range."
              ctaLabel="Browse everything"
              ctaHref="/catalog"
            />
          )}
        </div>
      </div>
    </>
  );
}
