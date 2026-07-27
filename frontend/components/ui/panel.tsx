import type { ReactNode } from "react";

import { LinkButton } from "./button";
import { cn } from "@/lib/cn";

/** The Jinja `panel` macro was a {% call %} block; children replace caller(). */
export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-card border border-border bg-surface shadow-card", className)}>
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-5 shadow-card">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  ctaLabel,
  ctaHref,
}: {
  title: ReactNode;
  body?: ReactNode;
  ctaLabel?: string;
  ctaHref?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-border bg-surface px-6 py-16 text-center">
      <p className="text-lg font-semibold text-ink">{title}</p>
      {body && <p className="max-w-sm text-sm text-ink-muted">{body}</p>}
      {ctaLabel && ctaHref && (
        <div className="pt-2">
          <LinkButton href={ctaHref}>{ctaLabel}</LinkButton>
        </div>
      )}
    </div>
  );
}
