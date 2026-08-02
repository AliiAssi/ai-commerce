import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { PlaceOrderButton } from "@/components/cart/place-order-button";
import { Price } from "@/components/ui/price";
import { ProductThumb } from "@/components/ui/product-image";
import { getCart } from "@/lib/api/cart";
import { getToken } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Checkout" };
export const dynamic = "force-dynamic";

export default async function CheckoutPage() {
  const token = await getToken();
  if (!token) redirect("/login?next=/checkout");

  const cart = await getCart(token);
  // nothing to buy: send them back rather than showing an empty order form
  if (cart.items.length === 0) redirect("/cart");

  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Checkout</h1>
      <div className="grid items-start gap-6 lg:grid-cols-[1fr_20rem]">
        <ul className="divide-y divide-border rounded-card border border-border bg-surface shadow-card">
          {cart.items.map((item) => (
            <li key={item.product_id} className="flex items-center gap-4 p-4">
              <ProductThumb
                src={item.image_url}
                alt=""
                size={48}
                className="h-12 w-12 rounded-el bg-surface-alt"
              />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{item.product_name}</p>
                <p className="text-xs text-ink-muted">
                  {item.quantity} &times; <Price value={item.unit_price} size="sm" />
                </p>
              </div>
              <Price value={item.line_total} size="sm" />
            </li>
          ))}
        </ul>

        <aside className="space-y-4 rounded-card border border-border bg-surface p-5 shadow-card">
          <h2 className="font-semibold">Payment</h2>
          <div className="flex items-center justify-between border-t border-border pt-3">
            <span className="font-medium">Total</span>
            <Price value={cart.grand_total} size="lg" />
          </div>
          <div className="rounded-el border border-border bg-surface-alt px-3 py-2 text-xs text-ink-muted">
            This demo store uses an <strong>instant fake payment</strong> — placing the order
            marks it as paid immediately, nothing is charged.
          </div>
          <PlaceOrderButton />
          <Link
            href="/cart"
            className="block text-center text-sm text-ink-muted hover:text-brand"
          >
            &larr; Back to cart
          </Link>
        </aside>
      </div>
    </>
  );
}
