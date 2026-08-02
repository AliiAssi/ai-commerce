"use client";

import { useState, useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Price } from "@/components/ui/price";
import type { AdminOrder } from "@/lib/api/types";
import { advanceOrder } from "@/lib/actions/admin";
import { FLASH_MS, useTransient } from "@/lib/client/use-transient";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";

// Only paid and shipped orders can move; delivered and cancelled are terminal.
const NEXT_STATUS: Partial<Record<AdminOrder["status"], string>> = {
  paid: "shipped",
  shipped: "delivered",
};

export function OrderRow({ order: initial }: { order: AdminOrder }) {
  const [order, setOrder] = useState(initial);
  const [changed, flash] = useTransient(FLASH_MS);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const next = NEXT_STATUS[order.status];

  const advance = () =>
    startTransition(async () => {
      const result = await advanceOrder(order.id);
      if (result.ok) {
        // the API returns the customer-facing Order, which has no user_email — keep ours
        setOrder({ ...order, ...result.data });
        // the badge beside the button now reads the new status; that is the confirmation
        flash();
      } else {
        toast(result.error, "danger");
      }
    });

  return (
    <tr className={cn(changed && "flash")}>
      <td className="px-4 py-3 font-medium">#{order.id}</td>
      <td className="max-w-56 truncate px-4 py-3 text-ink-muted">{order.user_email}</td>
      <td className="px-4 py-3 whitespace-nowrap text-ink-muted">
        {formatDateTime(order.created_at)}
      </td>
      <td className="px-4 py-3 text-ink-muted">{order.items.length}</td>
      <td className="px-4 py-3">
        <Price value={order.total} size="sm" />
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={order.status} />
      </td>
      <td className="px-4 py-3 text-right">
        {next ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={advance}
            disabled={pending}
          >
            Mark {next}
          </Button>
        ) : (
          <span className="text-xs text-ink-faint">&mdash;</span>
        )}
      </td>
    </tr>
  );
}
