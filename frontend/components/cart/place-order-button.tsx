"use client";

import { useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { placeOrder } from "@/lib/actions/orders";

export function PlaceOrderButton() {
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  return (
    <Button
      type="button"
      size="lg"
      block
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          // on success the action redirects, so anything returned here is a failure
          const result = await placeOrder();
          if (result && !result.ok) toast(result.error, "danger");
        })
      }
    >
      {pending ? "Placing…" : "Place order"}
    </Button>
  );
}
