import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const VARIANTS = {
  success: "border-success bg-success-subtle text-success",
  danger: "border-danger bg-danger-subtle text-danger",
  warning: "border-warning bg-warning-subtle text-warning",
  info: "border-brand bg-brand-subtle text-brand",
} as const;

export type ToastVariant = keyof typeof VARIANTS;

/** Presentational only. The provider that queues and auto-dismisses these lands in Phase 3. */
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
      role="status"
      data-toast
    >
      {children}
    </div>
  );
}
