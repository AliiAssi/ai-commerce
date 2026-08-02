"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { adjustStock } from "@/lib/actions/admin";
import { useTransient } from "@/lib/client/use-transient";

/** The dashboard's one-click restock on a low-stock row. */
export function RestockButton({
  productId,
  delta = 10,
}: {
  productId: number;
  delta?: number;
}) {
  const [done, confirmDone] = useTransient();
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          const result = await adjustStock(productId, delta);
          // the refresh redraws the row with the new stock; the tick only marks which button
          if (result.ok) {
            confirmDone();
            router.refresh();
          } else {
            toast(result.error, "danger");
          }
        })
      }
    >
      {done ? "✓" : `+${delta}`}
    </Button>
  );
}
