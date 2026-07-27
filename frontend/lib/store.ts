/** The Jinja app injected these as Jinja globals in main.py; here they are plain constants. */
export const STORE_NAME = "BEIT";

/**
 * Mirrors the Jinja `ai_enabled` global, which was `bool(AI_SERVICE_URL and INTERNAL_API_KEY)`.
 * The frontend cannot see the backend's env, so it gets its own flag; default on, set
 * AI_ENABLED=false to hide the widget entirely rather than show one that always errors.
 * Read only in Server Components, so it never reaches the browser as a value.
 */
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
