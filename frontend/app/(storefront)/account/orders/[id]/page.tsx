import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { CancelOrderButton } from "@/components/account/cancel-order-button";
import { StatusBadge } from "@/components/ui/badge";
import { Price } from "@/components/ui/price";
import { ApiError } from "@/lib/api/client";
import { getOrder } from "@/lib/api/orders";
import { getToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Order" };
export const dynamic = "force-dynamic";

export default async function OrderDetailPage(props: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await props.params;
  const token = await getToken();
  if (!token) redirect(`/login?next=/account/orders/${idParam}`);

  const id = Number.parseInt(idParam, 10);
  if (!Number.isInteger(id) || id <= 0) notFound();

  let order;
  try {
    order = await getOrder(token, id);
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isForbidden)) notFound();
    throw error;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link href="/account/orders" className="text-sm text-ink-muted hover:text-brand">
        &larr; My orders
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Order #{order.id}</h1>
        <StatusBadge status={order.status} />
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        Placed {formatDateTime(order.created_at)}
        {order.updated_at !== order.created_at && (
          <> &middot; updated {formatDateTime(order.updated_at)}</>
        )}
      </p>

      <ul className="mt-6 divide-y divide-border rounded-card border border-border bg-surface shadow-card">
        {order.items.map((item) => (
          <li key={item.product_id} className="flex items-center justify-between gap-4 p-4">
            <div>
              <Link
                href={`/products/${item.product_id}`}
                className="font-medium hover:text-brand"
              >
                {item.product_name}
              </Link>
              <p className="text-xs text-ink-muted">
                {item.quantity} &times; <Price value={item.unit_price} size="sm" />
              </p>
            </div>
            <Price value={item.line_total} size="sm" />
          </li>
        ))}
        <li className="flex items-center justify-between p-4">
          <span className="font-semibold">Total</span>
          <Price value={order.total} size="lg" />
        </li>
      </ul>

      {/* Only a paid order can still be cancelled; shipped and later cannot. */}
      {order.status === "paid" && <CancelOrderButton orderId={order.id} />}
    </div>
  );
}
