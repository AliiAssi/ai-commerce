"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useOptimistic,
  useTransition,
} from "react";
import type { MouseEvent, ReactNode } from "react";

import { FilterLink } from "@/components/ui/links";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/cn";
import { isPendingHref, optimisticParam } from "@/lib/nav-pending";

interface CatalogNav {
  pendingHref: string | null;
  category: string;
  navigate: (href: string) => void;
}

const CatalogNavContext = createContext<CatalogNav | null>(null);

export function CatalogNavProvider({
  category,
  children,
}: {
  category: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [pendingHref, setPendingHref] = useOptimistic<string | null, string>(
    null,
    (_, href) => href,
  );

  const navigate = useCallback(
    (href: string) => {
      startTransition(() => {
        setPendingHref(href);
        router.push(href);
      });
    },
    [router, setPendingHref],
  );

  const value = useMemo<CatalogNav>(
    () => ({
      pendingHref,
      navigate,
      category: optimisticParam(pendingHref, category, "category"),
    }),
    [pendingHref, navigate, category],
  );

  return <CatalogNavContext.Provider value={value}>{children}</CatalogNavContext.Provider>;
}

/** Null outside a provider: <Pagination> is shared with admin, which has no catalog nav. */
export function useCatalogNav(): CatalogNav | null {
  return useContext(CatalogNavContext);
}

/** Modified and middle clicks belong to the browser — only a plain click is intercepted. */
function isPlainClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

function useNavigation(href: string) {
  const nav = useCatalogNav();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!nav || !isPlainClick(event)) return;
    event.preventDefault();
    nav.navigate(href);
  };
  return { onClick, pending: isPendingHref(nav?.pendingHref ?? null, href) };
}

/**
 * A catalog navigation link. Still a real <a href>, so a JS-disabled browser navigates
 * exactly as it does today; the click handler only upgrades it to a tracked transition.
 */
export function CatalogLink({
  href,
  className,
  children,
  prefetch,
  ...rest
}: {
  href: string;
  className?: string;
  children: ReactNode;
  prefetch?: boolean;
  dir?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}) {
  const { onClick, pending } = useNavigation(href);

  return (
    <Link href={href} prefetch={prefetch} className={className} onClick={onClick} {...rest}>
      {children}
      {pending && <Spinner />}
    </Link>
  );
}

/** A rail row. Active state is optimistic: it lights up before the payload lands. */
export function CategoryLink({
  href,
  slug,
  name,
  count,
}: {
  href: string;
  slug: string;
  name: string;
  count: number;
}) {
  const nav = useCatalogNav();
  const { onClick, pending } = useNavigation(href);

  return (
    <FilterLink
      href={href}
      name={name}
      count={count}
      active={(nav?.category ?? "") === slug}
      pending={pending}
      onClick={onClick}
    />
  );
}

/** The results still on screen while a different URL loads. */
export function StaleResults({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const nav = useCatalogNav();
  const stale = Boolean(nav?.pendingHref);

  return (
    <div
      className={cn(className, stale && "is-stale")}
      aria-busy={stale || undefined}
      data-testid="catalog-results"
    >
      {children}
    </div>
  );
}

/** Mirrors the rail's optimistic state so the heading cannot disagree with the lit row. */
export function CatalogHeading({ category }: { category: string }) {
  const nav = useCatalogNav();
  const active = nav?.category ?? category;
  return <>{active ? active.replaceAll("-", " ") : "Everything"}</>;
}
