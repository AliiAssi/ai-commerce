import Link from "next/link";

import { listCategories } from "@/lib/api/catalog";
import type { Category } from "@/lib/api/types";
import { STORE_NAME } from "@/lib/store";
import { FooterAccountLinks } from "./footer-account";
import { FooterLink } from "@/components/ui/links";
import { Eyebrow } from "@/components/ui/typography";

async function Shelves() {
  let categories: Category[] = [];
  try {
    categories = await listCategories();
  } catch {
    categories = [];
  }

  return (
    <>
      {categories.map((category) => (
        <FooterLink
          key={category.id}
          href={`/catalog?category=${category.slug}`}
          count={category.product_count}
        >
          {category.name}
        </FooterLink>
      ))}
      <FooterLink href="/catalog">Everything</FooterLink>
    </>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto grid w-full max-w-shell gap-x-8 gap-y-12 px-4 py-16 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" className="font-serif text-xl tracking-mark text-ink">
            {STORE_NAME}
          </Link>
          <p className="mt-5 max-w-[30ch] text-sm leading-relaxed text-ink-muted">
            Everything Lebanon makes well, in one small store, sourced directly from the people
            who make it.
          </p>
          <p
            className="mt-8 font-serif text-5xl leading-none text-ink opacity-10 select-none"
            aria-hidden="true"
          >
            بيت
          </p>
        </div>

        <nav aria-label="The shelves">
          <h2 className="mb-4">
            <Eyebrow>The shelves</Eyebrow>
          </h2>
          <div className="flex flex-col">
            <Shelves />
          </div>
        </nav>

        <nav aria-label="The store">
          <h2 className="mb-4">
            <Eyebrow>The store</Eyebrow>
          </h2>
          <div className="flex flex-col">
            <FooterLink href="/about">About {STORE_NAME}</FooterLink>
            <FooterLink href="/makers">The makers</FooterLink>
            <FooterLink href="/shipping">Shipping &amp; returns</FooterLink>
          </div>
        </nav>

        <nav aria-label="Account">
          <h2 className="mb-4">
            <Eyebrow>Account</Eyebrow>
          </h2>
          <div className="flex flex-col">
            <FooterAccountLinks />
          </div>
        </nav>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex w-full max-w-shell flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-5 text-xs text-ink-muted">
          <span>&copy; {STORE_NAME}. Lebanese goods, sourced from the makers</span>
          <span>Instant fake payments &middot; nothing is charged</span>
        </div>
      </div>
    </footer>
  );
}
