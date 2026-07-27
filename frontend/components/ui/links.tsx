import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A primary navigation link. The active page keeps the brand underline lit. */
export function NavLink({
  href,
  active = false,
  children,
}: {
  href: string;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "border-b py-1 transition-colors",
        active
          ? "border-brand text-ink"
          : "border-transparent text-ink-muted hover:border-brand hover:text-ink",
      )}
    >
      {children}
    </Link>
  );
}

/** A row in a footer directory column; shelf rows carry their count. */
export function FooterLink({
  href,
  children,
  count,
}: {
  href: string;
  children: ReactNode;
  count?: number;
}) {
  return (
    <Link
      href={href}
      className="flex items-baseline justify-between gap-3 py-1 text-sm text-ink-muted transition-colors hover:text-ink"
    >
      <span>{children}</span>
      {count !== undefined && <span className="tabular-nums text-ink-faint">{count}</span>}
    </Link>
  );
}

/**
 * A filter in the catalog rail. A plain navigation on purpose: it changes the URL, which is
 * what drives the whole catalog page, so the rail's own active state can never go stale.
 */
export function FilterLink({
  href,
  name,
  count,
  active = false,
}: {
  href: string;
  name: string;
  count: number;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex items-baseline justify-between gap-3 py-1.5 text-sm transition-colors",
        active ? "text-brand" : "text-ink-muted hover:text-ink",
      )}
    >
      <span>
        {active && <span aria-hidden="true">— </span>}
        {name}
      </span>
      <span className="tabular-nums text-ink-faint">{count}</span>
    </Link>
  );
}

/** A row in the printed contents list of categories. */
export function IndexRow({
  number,
  name,
  count,
  href,
}: {
  number: number;
  name: string;
  count: number;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="grid grid-cols-[2.5rem_1fr_auto] items-baseline gap-5 border-b border-border py-4 transition-[padding,background] duration-base hover:bg-surface hover:ps-3"
    >
      <span className="text-sm tabular-nums text-ink-faint">
        {String(number).padStart(2, "0")}
      </span>
      <span className="font-serif text-xl">{name}</span>
      <span className="text-sm tabular-nums text-ink-faint">{count}</span>
    </Link>
  );
}
