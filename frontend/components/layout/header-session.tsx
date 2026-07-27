"use client";

import Link from "next/link";

import { useSession } from "@/lib/client/session-store";
import { LinkButton } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LogoutButton } from "@/components/auth/logout-button";

/** The bag icon, with the count once the session has loaded. */
export function CartBadge() {
  const { cartQuantity, loaded } = useSession();
  const showCount = loaded && cartQuantity > 0;

  return (
    <Link
      href="/cart"
      aria-label={
        showCount ? `Cart (${cartQuantity} item${cartQuantity === 1 ? "" : "s"})` : "Cart"
      }
      className="relative grid h-9 w-9 place-items-center rounded-el text-ink-muted transition-colors hover:text-brand"
    >
      <Icon name="bag" className="h-5 w-5" />
      {showCount && (
        <span
          aria-hidden="true"
          className="absolute end-0 top-0 min-w-[1.125rem] rounded-full bg-brand px-1 text-center text-[0.625rem] leading-[1.125rem] font-semibold text-brand-contrast"
        >
          {cartQuantity}
        </span>
      )}
    </Link>
  );
}

/** Desktop account area: nothing while loading, then either the menu or the two links. */
export function AccountMenu() {
  const { user, loaded } = useSession();

  if (!loaded) return <div className="hidden w-24 lg:block" aria-hidden="true" />;

  if (!user) {
    return (
      <div className="hidden items-center gap-4 ps-2 lg:flex">
        <Link
          href="/login"
          className="text-sm text-ink-muted transition-colors hover:text-brand"
        >
          Log in
        </Link>
        <LinkButton href="/register" size="sm">
          Sign up
        </LinkButton>
      </div>
    );
  }

  return (
    <details className="menu relative hidden lg:block">
      <summary className="flex items-center gap-1.5 py-1 ps-2 text-sm text-ink-muted transition-colors hover:text-brand">
        <span className="max-w-[14rem] truncate">{user.email || "Account"}</span>
        <Icon name="chevron-down" className="h-3 w-3" />
      </summary>
      <div className="absolute end-0 mt-2 w-44 rounded-card border border-border bg-surface p-1 text-sm shadow-pop">
        {user.role === "admin" && (
          <Link
            href="/admin"
            className="block rounded-el px-3 py-2 text-brand hover:bg-surface-alt"
          >
            Admin panel
          </Link>
        )}
        <Link
          href="/account/orders"
          className="block rounded-el px-3 py-2 hover:bg-surface-alt"
        >
          My orders
        </Link>
        <LogoutButton className="w-full rounded-el px-3 py-2 text-left text-danger hover:bg-surface-alt" />
      </div>
    </details>
  );
}

/** The account block inside the mobile disclosure panel. */
export function MobileAccountLinks() {
  const { user, loaded } = useSession();
  if (!loaded) return null;

  if (!user) {
    return (
      <>
        <Link href="/login" className="block py-2 text-sm text-ink-muted">
          Log in
        </Link>
        <Link href="/register" className="block py-2 text-sm text-brand">
          Create an account
        </Link>
      </>
    );
  }

  return (
    <>
      <p className="mb-2 text-[0.6875rem] tracking-label text-ink-faint uppercase">
        {user.email || "Account"}
      </p>
      {user.role === "admin" && (
        <Link href="/admin" className="block py-2 text-sm text-brand">
          Admin panel
        </Link>
      )}
      <Link href="/account/orders" className="block py-2 text-sm text-ink-muted">
        My orders
      </Link>
      <LogoutButton className="block py-2 text-sm text-danger" />
    </>
  );
}
