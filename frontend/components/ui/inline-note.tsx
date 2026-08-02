import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const TONES = {
  danger: "text-danger",
  success: "text-success",
  warning: "text-warning",
} as const;

export type NoteTone = keyof typeof TONES;

export function InlineNote({
  tone = "danger",
  children,
  className,
  ...rest
}: {
  tone?: NoteTone;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}) {
  return (
    <p
      role={tone === "danger" ? "alert" : "status"}
      className={cn("text-xs", TONES[tone], className)}
      {...rest}
    >
      {children}
    </p>
  );
}
