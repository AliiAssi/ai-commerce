import type { ReactNode } from "react";

import type { OrderStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const BASE = "inline-flex items-center rounded-el px-2 py-0.5 text-xs font-medium";

const VARIANTS = {
  neutral: "bg-surface-alt text-ink-muted border border-border",
  brand: "bg-brand-subtle text-brand",
  success: "bg-success-subtle text-success",
  warning: "bg-warning-subtle text-warning",
  danger: "bg-danger-subtle text-danger",
} as const;

export type BadgeVariant = keyof typeof VARIANTS;

export function Badge({
  children,
  variant = "neutral",
}: {
  children: ReactNode;
  variant?: BadgeVariant;
}) {
  return <span className={cn(BASE, VARIANTS[variant])}>{children}</span>;
}

/** Threshold matches LOW_STOCK_THRESHOLD on the backend. */
export const LOW_STOCK_AT = 5;

export function StockBadge({ stock }: { stock: number }) {
  if (stock <= 0) return <Badge variant="danger">Out of stock</Badge>;
  if (stock <= LOW_STOCK_AT) return <Badge variant="warning">Only {stock} left</Badge>;
  return <Badge variant="success">In stock</Badge>;
}

const STATUS_VARIANTS: Record<OrderStatus, BadgeVariant> = {
  paid: "brand",
  shipped: "warning",
  delivered: "success",
  cancelled: "neutral",
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return <Badge variant={STATUS_VARIANTS[status] ?? "neutral"}>{label}</Badge>;
}
