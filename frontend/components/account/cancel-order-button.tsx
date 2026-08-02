"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { InlineNote } from "@/components/ui/inline-note";
import { cancel } from "@/lib/actions/orders";

export function CancelOrderButton({ orderId }: { orderId: number }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const onClick = () => {
    if (!window.confirm("Cancel this order? Stock will be restored.")) return;

    startTransition(async () => {
      const result = await cancel(orderId);
      // The refresh flips the status badge to Cancelled and takes this button away, which
      // says more than a toast repeating what the page now shows.
      if (result.ok) {
        setError(null);
        router.refresh();
      } else {
        setError(result.error);
      }
    });
  };

  return (
    <div className="mt-6">
      <Button type="button" variant="danger-outline" onClick={onClick} disabled={pending}>
        {pending ? "Cancelling…" : "Cancel order"}
      </Button>
      {error ? (
        <InlineNote className="mt-2">{error}</InlineNote>
      ) : (
        <p className="mt-2 text-xs text-ink-faint">Orders can be cancelled until they ship.</p>
      )}
    </div>
  );
}
