"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { adjustStock } from "@/lib/actions/admin";

/** The dashboard's one-click restock on a low-stock row. */
export function RestockButton({
  productId,
  delta = 10,
}: {
  productId: number;
  delta?: number;
}) {
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
          if (result.ok) {
            toast(`Stock set to ${result.data.stock}`, "success");
            router.refresh();
          } else {
            toast(result.error, "danger");
          }
        })
      }
    >
      +{delta}
    </Button>
  );
}
