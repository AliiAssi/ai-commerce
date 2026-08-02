"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { setCartQuantity, useSession } from "@/lib/client/session-store";
import { useTransient } from "@/lib/client/use-transient";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { InlineNote } from "@/components/ui/inline-note";
import { Spinner } from "@/components/ui/spinner";
import { addToBag } from "@/lib/actions/cart";
import { UNAUTHENTICATED } from "@/lib/actions/codes";
import { cn } from "@/lib/cn";

function useAdd(productId: number) {
  const [pending, startTransition] = useTransition();
  const [added, confirmAdded] = useTransient();
  const { cartQuantity, user, loaded } = useSession();
  const toast = useToast();
  const router = useRouter();

  const toLogin = () => router.push(`/login?next=/products/${productId}`);

  const add = (quantity: number) => {
    // Only a *known* signed-out visitor is short-circuited. `user` is also null while the
    // session is still loading, and treating that as signed out bounced signed-in shoppers to
    // the login page if they clicked before /api/session answered. The client cannot read the
    // httpOnly cookie, so when it does not know yet, the server decides.
    if (loaded && !user) {
      toLogin();
      return;
    }

    // move the badge immediately; the action's response is the source of truth
    setCartQuantity(cartQuantity + quantity);
    startTransition(async () => {
      const result = await addToBag(productId, quantity);
      if (result.ok) {
        setCartQuantity(result.data.total_quantity);
        // The badge has already moved and the control says so itself; a toast on top of two
        // existing signals is the noise this pass removes.
        confirmAdded();
        return;
      }
      setCartQuantity(cartQuantity);
      if (result.code === UNAUTHENTICATED) toLogin();
      else toast(result.error, "danger");
    });
  };

  return { add, pending, added };
}

/** The quick-add control that surfaces on a catalogue plate on hover or focus. */
export function QuickAdd({
  productId,
  productName,
}: {
  productId: number;
  productName: string;
}) {
  const { add, pending, added } = useAdd(productId);

  return (
    <button
      type="button"
      onClick={() => add(1)}
      disabled={pending}
      aria-label={`Add ${productName} to bag`}
      data-added={added || undefined}
      className={cn(
        "plate-add absolute right-2.5 bottom-2.5 grid h-9 w-9 place-items-center rounded-el border transition-colors",
        added
          ? "border-success bg-success text-brand-contrast"
          : "border-border bg-surface text-ink hover:border-brand hover:bg-brand hover:text-brand-contrast",
      )}
    >
      <span aria-hidden="true">{added ? "✓" : "+"}</span>
      {added && <span className="sr-only">Added to your bag</span>}
    </button>
  );
}

/** The product page's quantity picker and Add to bag button. */
export function AddToBagForm({ productId, stock }: { productId: number; stock: number }) {
  const [quantity, setQuantity] = useState(1);
  const { add, pending, added } = useAdd(productId);

  return (
    <div className="flex items-center gap-4 pt-1">
      <input
        type="number"
        min={1}
        max={stock}
        value={quantity}
        onChange={(event) => setQuantity(Math.max(1, Number(event.target.value)))}
        aria-label="Quantity"
        className="w-20 rounded-el border border-border bg-surface px-3 py-2.5 text-center text-sm focus:border-brand focus:outline-none"
      />
      <Button type="button" size="lg" onClick={() => add(quantity)} disabled={pending}>
        {added ? "Added ✓" : "Add to bag"}
      </Button>
      {pending && <Spinner />}
      {added && (
        <InlineNote tone="success">
          <Link href="/cart" className="underline hover:text-brand">
            View your bag
          </Link>
        </InlineNote>
      )}
    </div>
  );
}
