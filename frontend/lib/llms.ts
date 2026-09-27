import type { Category, Product } from "@/lib/api/types";
import { absoluteUrl } from "@/lib/seo";
import { AUTHOR, SOURCE_URL, STORE_NAME } from "@/lib/store";

const PAGES = [
  { name: "Home", path: "/", note: "the shelves and the best rated goods" },
  {
    name: "Catalog",
    path: "/catalog",
    note: "every good, filterable by shelf, origin and price",
  },
  { name: "About", path: "/about", note: "what the store is and how it chooses what to stock" },
  {
    name: "The makers",
    path: "/makers",
    note: "the presses, kilns, kitchens and workshops behind the goods",
  },
  {
    name: "Shipping & returns",
    path: "/shipping",
    note: "how ordering works in this demonstration store",
  },
];

function link(name: string, path: string, note: string): string {
  return `- [${name}](${absoluteUrl(path)}): ${note}`;
}

function firstSentence(text: string): string {
  const match = text.match(/^.*?[.!?](?=\s|$)/);
  return (match ? match[0] : text).trim();
}

function productNote(product: Product): string {
  const facts = [`$${Number(product.price).toFixed(2)}`];
  if (product.origin) facts.push(product.origin);
  if (product.stock <= 0) facts.push("out of stock");
  if (product.review_count > 0) {
    facts.push(`rated ${Number(product.rating_avg).toFixed(1)}/5 by ${product.review_count}`);
  }
  return `${facts.join(", ")}. ${firstSentence(product.description)}`;
}

export function llmsText(categories: Category[], products: Product[]): string {
  const sections = [
    `# ${STORE_NAME}`,
    `> ${STORE_NAME} (بيت, "home") is a small online store of Lebanese goods sourced directly from the people who make them. It is a working demonstration store and portfolio project: browsing, search, the bag, checkout and reviews all work, but payments are simulated and nothing is ever charged or shipped.`,
    [
      `Built by ${AUTHOR.name} (${AUTHOR.github}), contact ${AUTHOR.email}. Source code: ${SOURCE_URL}.`,
      "Prices are in USD. Each product page lists its origin, price, stock and customer reviews. Search understands English and Arabic.",
    ].join("\n\n"),
    ["## Pages", ...PAGES.map((page) => link(page.name, page.path, page.note))].join("\n"),
  ];

  if (categories.length) {
    sections.push(
      [
        "## Shelves",
        ...categories.map((category) =>
          link(
            category.name,
            `/catalog?category=${category.slug}`,
            category.product_count === 1 ? "1 good" : `${category.product_count} goods`,
          ),
        ),
      ].join("\n"),
    );
  }

  if (products.length) {
    sections.push(
      [
        "## Products",
        ...products.map((product) =>
          link(product.name, `/products/${product.id}`, productNote(product)),
        ),
      ].join("\n"),
    );
  }

  sections.push(
    [
      "## Optional",
      `- [Source code](${SOURCE_URL}): the Next.js storefront, FastAPI services and AI search`,
      `- [Sitemap](${absoluteUrl("/sitemap.xml")}): every indexable URL`,
    ].join("\n"),
  );

  return `${sections.join("\n\n")}\n`;
}
