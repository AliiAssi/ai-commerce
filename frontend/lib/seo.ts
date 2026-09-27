import type { Metadata } from "next";

import type { Category, Product } from "@/lib/api/types";
import { AUTHOR, SOURCE_URL, STORE_NAME } from "@/lib/store";

const productionHost = process.env.VERCEL_PROJECT_PRODUCTION_URL;

/** Canonical origin: preview deployments still point search engines at production. */
export const SITE_URL =
  process.env.SITE_URL ??
  (productionHost ? `https://${productionHost}` : "http://localhost:3000");

export const SITE_TITLE = `${STORE_NAME} · Lebanese olive oil, za'atar, soap and handmade crafts`;

export const SITE_DESCRIPTION =
  "Everything Lebanon makes well, in one small store: Koura olive oil, Bekaa za'atar, Tripoli soap, Beit Chabab pottery and cedar woodwork, bought from the makers.";

export const GOOGLE_SITE_VERIFICATION = "UPY8valrbTERvhTzneAdoYWUDxck3xRbKOkF3-2FNBQ";

// A page that sets its own openGraph replaces the parent's wholesale, file-based image
// included, so the shared card has to travel with the defaults.
export const OPEN_GRAPH_DEFAULTS = {
  type: "website",
  siteName: STORE_NAME,
  locale: "en_US",
  images: [
    {
      url: "/opengraph-image",
      width: 1200,
      height: 630,
      alt: `${STORE_NAME}, Lebanese goods sourced from the makers`,
    },
  ],
};

export const NO_INDEX: Metadata["robots"] = { index: false, follow: true };

export function pageMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      ...OPEN_GRAPH_DEFAULTS,
      title: `${title} · ${STORE_NAME}`,
      description,
      url: path,
    },
  };
}

export function categoryDescription(category: Category): string {
  const goods = category.product_count === 1 ? "1 good" : `${category.product_count} goods`;
  return `${category.name} from Lebanon, bought directly from the people who make it. ${goods}, each with its origin, price and customer reviews.`;
}

export function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}

export function identitySchema() {
  const author = {
    "@type": "Person",
    "@id": absoluteUrl("/#author"),
    name: AUTHOR.name,
    url: AUTHOR.github,
    email: `mailto:${AUTHOR.email}`,
    sameAs: [AUTHOR.github],
  };
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": absoluteUrl("/#organization"),
        name: STORE_NAME,
        url: absoluteUrl("/"),
        logo: absoluteUrl("/icon.png"),
        description: SITE_DESCRIPTION,
        founder: { "@id": author["@id"] },
        sameAs: [SOURCE_URL],
      },
      {
        "@type": "WebSite",
        "@id": absoluteUrl("/#website"),
        name: STORE_NAME,
        url: absoluteUrl("/"),
        inLanguage: "en",
        publisher: { "@id": absoluteUrl("/#organization") },
        potentialAction: {
          "@type": "SearchAction",
          target: `${absoluteUrl("/catalog")}?q={search_term_string}`,
          "query-input": "required name=search_term_string",
        },
      },
      author,
    ],
  };
}

export function breadcrumbSchema(product: Product) {
  const trail = [
    { name: "Home", path: "/" },
    { name: product.category_name, path: `/catalog?category=${product.category_slug}` },
    { name: product.name, path: `/products/${product.id}` },
  ];
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: absoluteUrl(crumb.path),
    })),
  };
}
