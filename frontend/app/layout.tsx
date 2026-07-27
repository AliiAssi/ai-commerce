import type { Metadata } from "next";

import { ToastProvider } from "@/components/providers/toast-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "BEIT",
    template: "%s · BEIT",
  },
  description: "A curated store of Lebanese goods, made by hand.",
};

// Runs before first paint so a saved theme choice never flashes. The Jinja app inlined this
// in the storefront layout only, which is why its admin area flashed on reload; putting it in
// the root layout covers every route.
const THEME_SCRIPT = `try{var t=localStorage.getItem("theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col antialiased">
        {/* A client component holding no server data, so wrapping the root layout in it does
            not opt any route out of static prerendering. The session needs no provider — it
            is a module store in lib/client/session-store.ts. */}
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
