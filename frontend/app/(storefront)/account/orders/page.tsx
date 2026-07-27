import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { StatusBadge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/panel";
import { Price } from "@/components/ui/price";
import { listOrders } from "@/lib/api/orders";
import { getToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "My orders" };
export const dynamic = "force-dynamic";

export default async function OrdersPage() {
  const token = await getToken();
  if (!token) redirect("/login?next=/account/orders");

  const orders = await listOrders(token);

  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">My orders</h1>
      {orders.length === 0 ? (
        <EmptyState
          title="No orders yet"
          body="Your orders will show up here after checkout."
          ctaLabel="Browse catalog"
          ctaHref="/catalog"
        />
      ) : (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface shadow-card">
          {orders.map((order) => (
            <li key={order.id}>
              <Link
                href={`/account/orders/${order.id}`}
                className="flex flex-wrap items-center gap-3 p-4 hover:bg-surface-alt"
              >
                <span className="font-medium">Order #{order.id}</span>
                <span className="text-sm text-ink-muted">{formatDate(order.created_at)}</span>
                <StatusBadge status={order.status} />
                <span className="text-sm text-ink-muted">
                  {order.items.length} item{order.items.length === 1 ? "" : "s"}
                </span>
                <span className="ml-auto">
                  <Price value={order.total} />
                </span>
                <span className="text-ink-faint" aria-hidden="true">
                  &rarr;
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
