import { Analytics } from "@vercel/analytics/next";
import type { Metadata } from "next";

import { ToastProvider } from "@/components/providers/toast-provider";
import {
  GOOGLE_SITE_VERIFICATION,
  OPEN_GRAPH_DEFAULTS,
  SITE_DESCRIPTION,
  SITE_TITLE,
  SITE_URL,
} from "@/lib/seo";
import { AUTHOR, STORE_NAME } from "@/lib/store";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: `%s · ${STORE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: STORE_NAME,
  authors: [{ name: AUTHOR.name, url: AUTHOR.github }],
  creator: AUTHOR.name,
  openGraph: { ...OPEN_GRAPH_DEFAULTS, title: SITE_TITLE, description: SITE_DESCRIPTION },
  twitter: { card: "summary_large_image" },
  verification: GOOGLE_SITE_VERIFICATION ? { google: GOOGLE_SITE_VERIFICATION } : undefined,
};

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
        <Analytics />
      </body>
    </html>
  );
}
