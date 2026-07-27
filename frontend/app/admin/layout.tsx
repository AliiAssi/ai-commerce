import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AdminLogout, AdminSidebarNav, AdminTopNav } from "@/components/admin/admin-nav";
import { EmptyState } from "@/components/ui/panel";
import { getCurrentUser } from "@/lib/auth/session";
import { STORE_NAME } from "@/lib/store";

export const metadata: Metadata = { title: "Admin" };

// Permission-gated and per-user: never cached.
export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/admin");

  // The API is the real authority — every admin endpoint re-checks the role against the
  // database on each request. This only decides what to render, so a demoted admin still
  // cannot act even if they somehow reach a page.
  const permitted = user.role === "admin";

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar md:flex">
        <Link href="/admin" className="px-5 py-5 text-lg font-bold text-sidebar-ink-active">
          {STORE_NAME}{" "}
          <span className="text-xs font-medium tracking-wide text-sidebar-ink uppercase">
            admin
          </span>
        </Link>
        <AdminSidebarNav />
        <div className="px-3 pb-5">
          <Link
            href="/"
            className="block rounded-el px-3 py-2 text-sm text-sidebar-ink hover:text-sidebar-ink-active"
          >
            &larr; View store
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-border bg-surface">
          <div className="flex items-center gap-4 px-6 py-3">
            <AdminTopNav />
            <div className="ml-auto flex items-center gap-4 text-sm">
              <Link href="/" className="hidden text-ink-muted hover:text-brand md:inline">
                View store
              </Link>
              <span className="text-ink-muted">{user.email}</span>
              <AdminLogout />
            </div>
          </div>
        </header>

        <main className="min-w-0 flex-1 px-6 py-8">
          {permitted ? (
            children
          ) : (
            <EmptyState
              title="This area is restricted"
              body="Your account does not have admin access."
              ctaLabel="Back to the store"
              ctaHref="/"
            />
          )}
        </main>
      </div>
    </div>
  );
}
