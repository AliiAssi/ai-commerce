import type { ReactNode } from "react";

import { MenuDismiss } from "@/components/behaviour/menu-dismiss";
import { RevealOnScroll } from "@/components/behaviour/reveal-on-scroll";
import { ChatWidget } from "@/components/chat/chat-widget";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { aiEnabled } from "@/lib/store";

export default function StorefrontLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-shell flex-1 px-4 py-10">{children}</main>
      <SiteFooter />
      <RevealOnScroll />
      <MenuDismiss />
      {aiEnabled && <ChatWidget />}
    </>
  );
}
