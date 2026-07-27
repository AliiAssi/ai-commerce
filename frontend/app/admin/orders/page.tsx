import type { Metadata } from "next";
import Link from "next/link";

import { OrderRow } from "@/components/admin/order-row";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/panel";
import { getOrderStatusCounts, listAdminOrders } from "@/lib/api/admin";
import { ORDER_STATUSES, type OrderStatus } from "@/lib/api/types";
import { requireToken } from "@/lib/auth/session";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "Orders · Admin" };

const STATUS_VALUES = new Set<string>(ORDER_STATUSES);

const TABS: ReadonlyArray<{ value: "" | OrderStatus; label: string }> = [
  { value: "", label: "All" },
  { value: "paid", label: "Paid" },
  { value: "shipped", label: "Shipped" },
  { value: "delivered", label: "Delivered" },
  { value: "cancelled", label: "Cancelled" },
];

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function AdminOrdersPage(props: { searchParams: Promise<RawParams> }) {
  const raw = await props.searchParams;
  const statusRaw = one(raw.status);
  const status = STATUS_VALUES.has(statusRaw) ? (statusRaw as OrderStatus) : undefined;
  const pageNumber = Number.parseInt(one(raw.page), 10);
  const page = Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : 1;

  const token = await requireToken();
  // G2 and G3 — the admin order page and its status tabs
  const [result, counts] = await Promise.all([
    listAdminOrders(token, { status, page }),
    getOrderStatusCounts(token),
  ]);

  const query = new URLSearchParams();
  if (status) query.set("status", status);

  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Orders</h1>

      <div className="mb-6 flex flex-wrap gap-2">
        {TABS.map((tab) => {
          const active = (status ?? "") === tab.value;
          // G3 zero-fills every status, so this never has to guard a missing key
          const count = tab.value ? counts.counts[tab.value] : counts.total;
          return (
            <Link
              key={tab.value || "all"}
              href={tab.value ? `/admin/orders?status=${tab.value}` : "/admin/orders"}
              className={cn(
                "rounded-el border px-3 py-1.5 text-sm",
                active
                  ? "border-brand bg-brand-subtle font-medium text-brand"
                  : "border-border bg-surface text-ink-muted hover:border-brand hover:text-brand",
              )}
            >
              {tab.label} <span className="text-xs text-ink-faint">{count}</span>
            </Link>
          );
        })}
      </div>

      {result.items.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-card border border-border bg-surface shadow-card">
            <table className="w-full min-w-[46rem] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs tracking-wide text-ink-faint uppercase">
                  <th className="px-4 py-3 font-medium">Order</th>
                  <th className="px-4 py-3 font-medium">Customer</th>
                  <th className="px-4 py-3 font-medium">Placed</th>
                  <th className="px-4 py-3 font-medium">Items</th>
                  <th className="px-4 py-3 font-medium">Total</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.items.map((order) => (
                  <OrderRow key={order.id} order={order} />
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={result.page}
            pages={result.pages}
            baseUrl="/admin/orders"
            query={query}
          />
        </>
      ) : (
        <EmptyState title="No orders here" body="Orders will appear as customers check out." />
      )}
    </>
  );
}
