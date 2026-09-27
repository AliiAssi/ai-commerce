export const STORE_NAME = "BEIT";

export const AUTHOR = {
  name: "Ali Assi",
  github: "https://github.com/AliiAssi",
  email: "aliassii2025@gmail.com",
} as const;

export const SOURCE_URL = "https://github.com/AliiAssi/ai-commerce";

export const aiEnabled = process.env.AI_ENABLED !== "false";

export const NAV_ITEMS = [
  { label: "Catalog", href: "/catalog" },
  { label: "The makers", href: "/makers" },
  { label: "About", href: "/about" },
] as const;

/** Product pages belong to the catalog, so the underline stays lit there too. */
export function isNavActive(href: string, pathname: string): boolean {
  if (href === "/catalog") {
    return pathname.startsWith("/catalog") || pathname.startsWith("/products");
  }
  return pathname.startsWith(href);
}
