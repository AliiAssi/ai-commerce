import type { Metadata } from "next";
import Link from "next/link";

import { RestockButton } from "@/components/admin/restock-button";
import { Badge, StatusBadge, StockBadge } from "@/components/ui/badge";
import { Price } from "@/components/ui/price";
import { StatCard } from "@/components/ui/panel";
import { getDashboard } from "@/lib/api/admin";
import { ORDER_STATUSES } from "@/lib/api/types";
import { requireToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Dashboard · Admin" };

// G1 — the endpoint built in Phase 0. The Jinja dashboard reached IAdminService through the
// DI container; this is the same data over HTTP.
export default async function AdminDashboardPage() {
  const stats = await getDashboard(await requireToken());

  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Dashboard</h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Revenue"
          value={`$${Number(stats.revenue).toFixed(2)}`}
          hint="non-cancelled orders"
        />
        <StatCard label="Orders" value={stats.orders_total} />
        <StatCard
          label="Active products"
          value={stats.active_product_count}
          hint={`of ${stats.product_count} total`}
        />
        <StatCard label="Customers" value={stats.customer_count} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {ORDER_STATUSES.map((status) => (
          <Link
            key={status}
            href={`/admin/orders?status=${status}`}
            className="inline-flex items-center gap-2 rounded-el border border-border bg-surface px-3 py-1.5 text-sm hover:border-brand"
          >
            <StatusBadge status={status} />
            <span className="font-semibold">{stats.orders_by_status[status] ?? 0}</span>
          </Link>
        ))}
      </div>

      <div className="mt-8 grid items-start gap-6 xl:grid-cols-2">
        <section className="rounded-card border border-border bg-surface shadow-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="font-semibold">Low stock</h2>
            <Link
              href="/admin/products?status=low"
              className="text-sm text-brand hover:underline"
            >
              View all
            </Link>
          </div>
          {stats.low_stock.length > 0 ? (
            <ul className="divide-y divide-border">
              {stats.low_stock.map((product) => (
                <li key={product.id} className="flex items-center gap-3 px-5 py-3">
                  <Link
                    href={`/admin/products/${product.id}/edit`}
                    className="min-w-0 flex-1 truncate font-medium hover:text-brand"
                  >
                    {product.name}
                  </Link>
                  <StockBadge stock={product.stock} />
                  <RestockButton productId={product.id} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-8 text-sm text-ink-muted">Everything is well stocked.</p>
          )}
        </section>

        <section className="rounded-card border border-border bg-surface shadow-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="font-semibold">Recent orders</h2>
            <Link href="/admin/orders" className="text-sm text-brand hover:underline">
              View all
            </Link>
          </div>
          {stats.recent_orders.length > 0 ? (
            <ul className="divide-y divide-border">
              {stats.recent_orders.map((order) => (
                <li key={order.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                  <span className="font-medium">#{order.id}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-muted">
                    {order.user_email}
                  </span>
                  <StatusBadge status={order.status} />
                  <Price value={order.total} size="sm" />
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-8 text-sm text-ink-muted">No orders yet.</p>
          )}
        </section>
      </div>

      <section className="mt-6 rounded-card border border-border bg-surface shadow-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-semibold">Recent activity</h2>
          <Link href="/admin/audit" className="text-sm text-brand hover:underline">
            Full audit log
          </Link>
        </div>
        {stats.recent_activity.length > 0 ? (
          <ul className="divide-y divide-border">
            {stats.recent_activity.map((entry) => (
              <li
                key={entry.id}
                className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm"
              >
                <Badge variant="brand">{entry.action}</Badge>
                <span className="text-ink-muted">
                  {entry.entity_type}
                  {entry.entity_id ? ` #${entry.entity_id}` : ""}
                </span>
                <span className="min-w-0 flex-1 truncate text-ink-faint">
                  by {entry.admin_email}
                </span>
                <span className="text-xs text-ink-faint">
                  {formatDateTime(entry.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-sm text-ink-muted">No admin actions recorded yet.</p>
        )}
      </section>
    </>
  );
}
