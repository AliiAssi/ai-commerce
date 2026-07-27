"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { setCartQuantity, useSession } from "@/lib/client/session-store";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { addToBag } from "@/lib/actions/cart";

function useAdd(productId: number) {
  const [pending, startTransition] = useTransition();
  const { cartQuantity, user } = useSession();
  const toast = useToast();
  const router = useRouter();

  const add = (quantity: number) => {
    if (!user) {
      router.push(`/login?next=/products/${productId}`);
      return;
    }
    // move the badge immediately; the action's response is the source of truth
    setCartQuantity(cartQuantity + quantity);
    startTransition(async () => {
      const result = await addToBag(productId, quantity);
      if (result.ok) {
        setCartQuantity(result.data.total_quantity);
        toast("Added to your bag", "success");
      } else {
        setCartQuantity(cartQuantity);
        toast(result.error, "danger");
      }
    });
  };

  return { add, pending };
}

/** The quick-add control that surfaces on a catalogue plate on hover or focus. */
export function QuickAdd({
  productId,
  productName,
}: {
  productId: number;
  productName: string;
}) {
  const { add, pending } = useAdd(productId);

  return (
    <button
      type="button"
      onClick={() => add(1)}
      disabled={pending}
      aria-label={`Add ${productName} to bag`}
      className="plate-add absolute right-2.5 bottom-2.5 grid h-9 w-9 place-items-center rounded-el border border-border bg-surface text-ink transition-colors hover:border-brand hover:bg-brand hover:text-brand-contrast"
    >
      <span aria-hidden="true">+</span>
    </button>
  );
}

/** The product page's quantity picker and Add to bag button. */
export function AddToBagForm({ productId, stock }: { productId: number; stock: number }) {
  const [quantity, setQuantity] = useState(1);
  const { add, pending } = useAdd(productId);

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
        Add to bag
      </Button>
      {pending && <Spinner />}
    </div>
  );
}
