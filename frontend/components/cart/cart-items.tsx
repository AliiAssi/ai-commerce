"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { setCartQuantity } from "@/lib/client/session-store";
import { useToast } from "@/components/providers/toast-provider";
import { LinkButton } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/panel";
import { Price } from "@/components/ui/price";
import { ProductImage } from "@/components/ui/product-image";
import { removeFromBag, setQuantity } from "@/lib/actions/cart";
import type { Cart } from "@/lib/api/types";

/**
 * Optimistic by hand rather than with useOptimistic: the server returns the whole recomputed
 * cart (line totals, grand total, stock), so the win is showing the new numbers instantly and
 * then replacing them with the server's — not merely reordering a list. On failure the
 * previous cart is restored and the reason is toasted, which is what HTMX's error path did.
 */
export function CartItems({ initialCart }: { initialCart: Cart }) {
  const [cart, setCart] = useState(initialCart);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const apply = (
    optimistic: Cart,
    run: () => Promise<{ ok: boolean; data?: Cart; error?: string }>,
  ) => {
    const previous = cart;
    setCart(optimistic);
    setCartQuantity(optimistic.total_quantity);

    startTransition(async () => {
      const result = await run();
      if (result.ok && result.data) {
        setCart(result.data);
        setCartQuantity(result.data.total_quantity);
        return;
      }
      setCart(previous);
      setCartQuantity(previous.total_quantity);
      toast(result.error ?? "That didn't work", "danger");
    });
  };

  const recompute = (items: Cart["items"]): Cart => ({
    ...cart,
    items,
    total_quantity: items.reduce((sum, item) => sum + item.quantity, 0),
    grand_total: items
      .reduce((sum, item) => sum + Number(item.unit_price) * item.quantity, 0)
      .toFixed(2),
  });

  const changeQuantity = (productId: number, quantity: number) => {
    if (quantity < 1) return;
    const items = cart.items.map((item) =>
      item.product_id === productId
        ? {
            ...item,
            quantity,
            line_total: (Number(item.unit_price) * quantity).toFixed(2),
          }
        : item,
    );
    apply(recompute(items), () => setQuantity(productId, quantity));
  };

  const remove = (productId: number) => {
    const items = cart.items.filter((item) => item.product_id !== productId);
    apply(recompute(items), () => removeFromBag(productId));
  };

  if (cart.items.length === 0) {
    return (
      <EmptyState
        title="Your cart is empty"
        body="Find something you like in the catalog."
        ctaLabel="Browse catalog"
        ctaHref="/catalog"
      />
    );
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[1fr_20rem]">
      <ul className="divide-y divide-border rounded-card border border-border bg-surface shadow-card">
        {cart.items.map((item) => (
          <li key={item.product_id} className="flex items-center gap-4 p-4">
            <ProductImage
              src={item.image_url}
              alt=""
              className="h-16 w-16 rounded-el bg-surface-alt object-cover"
            />
            <div className="min-w-0 flex-1">
              <Link
                href={`/products/${item.product_id}`}
                className="font-medium hover:text-brand"
              >
                {item.product_name}
              </Link>
              <p className="mt-0.5 text-xs text-ink-muted">
                <Price value={item.unit_price} size="sm" /> each
                {item.quantity > item.available_stock && (
                  <>
                    {" · "}
                    <span className="text-danger">only {item.available_stock} in stock</span>
                  </>
                )}
              </p>
            </div>
            <input
              type="number"
              min={1}
              max={999}
              value={item.quantity}
              disabled={pending}
              aria-label={`Quantity of ${item.product_name}`}
              onChange={(event) => changeQuantity(item.product_id, Number(event.target.value))}
              className="w-16 rounded-el border border-border bg-surface px-2 py-1.5 text-center text-sm"
            />
            <span className="w-20 text-right">
              <Price value={item.line_total} size="sm" />
            </span>
            <button
              type="button"
              onClick={() => remove(item.product_id)}
              disabled={pending}
              className="text-ink-faint hover:text-danger"
              title={`Remove ${item.product_name}`}
              aria-label={`Remove ${item.product_name}`}
            >
              &#10005;
            </button>
          </li>
        ))}
      </ul>

      <aside className="space-y-3 rounded-card border border-border bg-surface p-5 shadow-card">
        <h2 className="font-semibold">Summary</h2>
        <div className="flex justify-between text-sm">
          <span className="text-ink-muted">Items</span>
          <span>{cart.total_quantity}</span>
        </div>
        <div className="flex items-center justify-between border-t border-border pt-3">
          <span className="font-medium">Total</span>
          <Price value={cart.grand_total} size="lg" />
        </div>
        <LinkButton href="/checkout" size="lg" block>
          Checkout
        </LinkButton>
        <p className="text-xs text-ink-faint">Instant fake payment, nothing is charged.</p>
      </aside>
    </div>
  );
}
