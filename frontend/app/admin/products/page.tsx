import type { Metadata } from "next";

import { ProductRow } from "@/components/admin/product-row";
import { Button, LinkButton } from "@/components/ui/button";
import { Field, SelectField } from "@/components/ui/field";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { listAdminProducts } from "@/lib/api/admin";
import { listCategories } from "@/lib/api/catalog";
import type { ProductStatusFilter } from "@/lib/api/types";
import { requireToken } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Products · Admin" };

const STATUSES: ReadonlyArray<{ value: ProductStatusFilter; text: string }> = [
  { value: "all", text: "All" },
  { value: "active", text: "Active" },
  { value: "archived", text: "Archived" },
  { value: "low", text: "Low stock" },
];

const STATUS_VALUES = new Set<string>(STATUSES.map((s) => s.value));

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function AdminProductsPage(props: { searchParams: Promise<RawParams> }) {
  const raw = await props.searchParams;
  const q = one(raw.q).trim();
  const category = one(raw.category).trim();
  const statusRaw = one(raw.status);
  const status = (STATUS_VALUES.has(statusRaw) ? statusRaw : "all") as ProductStatusFilter;
  const pageNumber = Number.parseInt(one(raw.page), 10);
  const page = Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : 1;

  const token = await requireToken();
  // G5 — the admin-only listing that can reach archived and low-stock rows
  const [result, categories] = await Promise.all([
    listAdminProducts(token, {
      q: q || undefined,
      category: category || undefined,
      status,
      page,
    }),
    listCategories(),
  ]);

  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (category) query.set("category", category);
  if (status !== "all") query.set("status", status);

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Products</h1>
        <LinkButton href="/admin/products/new">New product</LinkButton>
      </div>

      <form
        action="/admin/products"
        method="get"
        className="mb-6 grid items-end gap-3 rounded-card border border-border bg-surface p-4 shadow-card sm:grid-cols-2 lg:grid-cols-5"
      >
        <Field
          name="q"
          label="Search"
          type="search"
          defaultValue={q}
          placeholder="Name or description"
        />
        <SelectField
          name="category"
          label="Category"
          defaultValue={category}
          options={[
            { value: "", text: "All" },
            ...categories.map((c) => ({ value: c.slug, text: c.name })),
          ]}
        />
        <SelectField name="status" label="Status" defaultValue={status} options={STATUSES} />
        <div className="lg:col-span-2">
          <Button type="submit">Filter</Button>
        </div>
      </form>

      {result.items.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-card border border-border bg-surface shadow-card">
            <table className="w-full min-w-[42rem] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs tracking-wide text-ink-faint uppercase">
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="px-4 py-3 font-medium">Price</th>
                  <th className="px-4 py-3 font-medium">Stock</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.items.map((product) => (
                  <ProductRow key={product.id} product={product} />
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={result.page}
            pages={result.pages}
            baseUrl="/admin/products"
            query={query}
          />
        </>
      ) : (
        <EmptyState
          title="No products match"
          body="Try different filters."
          ctaLabel="Clear filters"
          ctaHref="/admin/products"
        />
      )}
    </>
  );
}
