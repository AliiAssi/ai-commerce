import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Eyebrow({
  children,
  tone = "faint",
}: {
  children: ReactNode;
  tone?: "faint" | "muted";
}) {
  return (
    <span
      className={cn(
        "text-[0.6875rem] uppercase tracking-label",
        tone === "muted" ? "text-ink-muted" : "text-ink-faint",
      )}
    >
      {children}
    </span>
  );
}
