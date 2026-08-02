import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const VARIANTS = {
  success: "border-success bg-success-subtle text-success",
  danger: "border-danger bg-danger-subtle text-danger",
  warning: "border-warning bg-warning-subtle text-warning",
  info: "border-brand bg-brand-subtle text-brand",
} as const;

export type ToastVariant = keyof typeof VARIANTS;

/**
 * Presentational only; the provider queues and dismisses these, and owns the live region.
 * Reserved for failures that belong to the page rather than to one control — everything a
 * control can report itself now says so in place, via <InlineNote> or its own label.
 */
export function Toast({
  children,
  variant = "info",
  leaving = false,
}: {
  children: ReactNode;
  variant?: ToastVariant;
  leaving?: boolean;
}) {
  return (
    <div
      className={cn(
        "toast rounded-el border px-4 py-3 text-sm",
        VARIANTS[variant],
        leaving && "toast-out",
      )}
      data-toast
    >
      {children}
    </div>
  );
}
