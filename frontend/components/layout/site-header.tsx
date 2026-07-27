"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { AccountMenu, CartBadge, MobileAccountLinks } from "./header-session";
import { SearchForm } from "./search-form";
import { ThemeToggle } from "./theme-toggle";
import { Icon } from "@/components/ui/icon";
import { NavLink } from "@/components/ui/links";
import { cn } from "@/lib/cn";
import { isNavActive, NAV_ITEMS, STORE_NAME } from "@/lib/store";

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <>
      {/* Utility strip — one quiet line above the masthead; scrolls away, never sticks. */}
      <div className="border-b border-border bg-ink px-4 py-2 text-center text-[0.625rem] tracking-label text-surface uppercase">
        <p className="mx-auto w-full max-w-shell">
          Sourced directly from makers across Lebanon
          <span className="hidden sm:inline">
            {" "}
            &middot; payments are simulated so nothing is charged
          </span>
        </p>
      </div>

      <header className="sticky top-0 z-40 border-b border-border bg-surface/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-shell items-center gap-5 px-4 py-4">
          <Link
            href="/"
            className="me-auto font-serif text-xl tracking-mark whitespace-nowrap text-ink"
          >
            {STORE_NAME}
          </Link>

          <nav aria-label="Primary" className="hidden items-center gap-6 text-sm lg:flex">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                active={isNavActive(item.href, pathname)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <Suspense fallback={null}>
            <SearchForm className="hidden max-w-xs flex-1 md:block" />
          </Suspense>

          <div className="flex items-center gap-1 sm:gap-2">
            <ThemeToggle />
            <CartBadge />
            <AccountMenu />

            {/* Mobile menu — a details disclosure whose panel hangs off the sticky header. */}
            <details className="menu lg:hidden">
              <summary
                className="grid h-9 w-9 place-items-center rounded-el text-ink-muted transition-colors hover:text-brand"
                aria-label="Menu"
              >
                <span className="when-closed">
                  <Icon name="menu" className="h-5 w-5" />
                </span>
                <span className="when-open">
                  <Icon name="close" className="h-5 w-5" />
                </span>
              </summary>
              <div className="absolute inset-x-0 top-full border-b border-border bg-surface shadow-pop lg:hidden">
                <nav aria-label="Mobile" className="mx-auto w-full max-w-shell px-4 py-2">
                  <div className="divide-y divide-border">
                    {NAV_ITEMS.map((item) => {
                      const active = isNavActive(item.href, pathname);
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex items-baseline justify-between gap-3 py-3.5 font-serif text-lg",
                            active ? "text-brand" : "text-ink",
                          )}
                        >
                          {item.label}
                          {active && (
                            <span aria-hidden="true" className="text-sm">
                              &mdash;
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                  <div className="border-t border-border py-4">
                    <MobileAccountLinks />
                  </div>
                </nav>
              </div>
            </details>
          </div>
        </div>

        <Suspense fallback={null}>
          <SearchForm className="border-t border-border px-4 py-2 md:hidden" />
        </Suspense>
      </header>
    </>
  );
}
