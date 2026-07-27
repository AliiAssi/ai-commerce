"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logoutAction } from "@/lib/actions/auth";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/admin", label: "Dashboard" },
  { href: "/admin/products", label: "Products" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/audit", label: "Audit log" },
] as const;

// /admin must not stay lit on /admin/products, so the dashboard matches exactly and the
// others match by prefix.
function isActive(href: string, pathname: string) {
  return href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
}

export function AdminSidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-1 flex-col gap-1 px-3">
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "rounded-el px-3 py-2 text-sm",
            isActive(item.href, pathname)
              ? "bg-sidebar-active font-medium text-sidebar-ink-active"
              : "text-sidebar-ink hover:text-sidebar-ink-active",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

export function AdminTopNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-3 overflow-x-auto text-sm md:hidden">
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "whitespace-nowrap",
            isActive(item.href, pathname) ? "font-semibold text-brand" : "text-ink-muted",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

export function AdminLogout() {
  return (
    <form action={logoutAction}>
      <button type="submit" className="text-danger hover:underline">
        Log out
      </button>
    </form>
  );
}
