import type { ReactNode } from "react";

import { MenuDismiss } from "@/components/behaviour/menu-dismiss";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";

// Same shell as the storefront; auth pages are a separate route group only so they can never
// be mistaken for cacheable storefront routes.
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-shell flex-1 px-4 py-10">{children}</main>
      <SiteFooter />
      <MenuDismiss />
    </>
  );
}
