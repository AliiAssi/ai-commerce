import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { LinkButton } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Price } from "@/components/ui/price";
import { ApiError } from "@/lib/api/client";
import { getOrder } from "@/lib/api/orders";
import { getToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Order confirmed" };
export const dynamic = "force-dynamic";

export default async function OrderConfirmationPage(props: {
  params: Promise<{ orderId: string }>;
}) {
  const { orderId } = await props.params;
  const token = await getToken();
  if (!token) redirect(`/login?next=/checkout/done/${orderId}`);

  const id = Number.parseInt(orderId, 10);
  if (!Number.isInteger(id) || id <= 0) notFound();

  let order;
  try {
    order = await getOrder(token, id);
  } catch (error) {
    // the API scopes orders to their owner, so someone else's id is a 404 here too
    if (error instanceof ApiError && (error.isNotFound || error.isForbidden)) notFound();
    throw error;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-card border border-border bg-surface p-8 text-center shadow-card">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-success-subtle text-2xl text-success">
          &#10003;
        </div>
        <h1 className="text-2xl font-bold">Thanks — order #{order.id} is confirmed</h1>
        <p className="mt-2 flex flex-wrap items-center justify-center gap-2 text-sm text-ink-muted">
          <span>Paid {formatDateTime(order.created_at)}</span>
          <span aria-hidden="true">&middot;</span>
          <StatusBadge status={order.status} />
        </p>
      </div>

      <ul className="mt-6 divide-y divide-border rounded-card border border-border bg-surface shadow-card">
        {order.items.map((item) => (
          <li key={item.product_id} className="flex items-center justify-between gap-4 p-4">
            <div>
              <p className="font-medium">{item.product_name}</p>
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

      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <LinkButton href="/account/orders" variant="secondary">
          View my orders
        </LinkButton>
        <LinkButton href="/catalog">Continue shopping</LinkButton>
      </div>
    </div>
  );
}
