import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * The uppercase utility line used for origins, eyebrows and counts.
 * Named Eyebrow rather than Label (the Jinja macro's name) so it is never confused with the
 * form Field's <label>.
 */
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
