"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { cancel } from "@/lib/actions/orders";

export function CancelOrderButton({ orderId }: { orderId: number }) {
  const [pending, startTransition] = useTransition();
  const toast = useToast();
  const router = useRouter();

  const onClick = () => {
    // same guard the Jinja form had via onsubmit="return confirm(...)"
    if (!window.confirm("Cancel this order? Stock will be restored.")) return;

    startTransition(async () => {
      const result = await cancel(orderId);
      if (result.ok) {
        toast(`Order #${orderId} cancelled`, "success");
        router.refresh();
      } else {
        toast(result.error, "danger");
      }
    });
  };

  return (
    <div className="mt-6">
      <Button type="button" variant="danger-outline" onClick={onClick} disabled={pending}>
        {pending ? "Cancelling…" : "Cancel order"}
      </Button>
      <p className="mt-2 text-xs text-ink-faint">Orders can be cancelled until they ship.</p>
    </div>
  );
}
