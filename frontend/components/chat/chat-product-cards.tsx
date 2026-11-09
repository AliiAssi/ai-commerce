"use client";

import { Price } from "@/components/ui/price";
import { ProductThumb } from "@/components/ui/product-image";
import { Stars } from "@/components/ui/stars";
import { trackAssistantClick } from "@/lib/client/assistant-analytics";
import { isStorePath } from "@/lib/client/markdown";
import type { ChatMore, ChatProduct } from "@/lib/client/sse";

export function ChatProductCards({
  products,
  more,
}: {
  products: ChatProduct[];
  more?: ChatMore | null;
}) {
  const cards = products.filter((product) => isStorePath(product.url));
  if (cards.length === 0) return null;

  return (
    <div className="w-full max-w-[80%] space-y-2">
      <ul className="space-y-2" aria-label="Products mentioned">
        {cards.map((product) => (
          <li key={product.id}>
            <a
              href={product.url}
              target="_blank"
              rel="noopener"
              onClick={() => trackAssistantClick("card", product.url)}
              className="flex items-center gap-3 rounded-card border border-border bg-surface p-2 shadow-card transition-colors duration-fast hover:border-brand"
            >
              <ProductThumb
                src={product.image_url}
                alt=""
                size={48}
                className="h-12 w-12 shrink-0 rounded-el bg-surface-alt"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">
                  {product.name}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2">
                  <Price value={product.price} size="sm" />
                  {product.review_count > 0 && (
                    <Stars rating={product.rating_avg} count={product.review_count} />
                  )}
                  {product.stock <= 0 && (
                    <span className="text-xs text-danger">Out of stock</span>
                  )}
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
      {more && isStorePath(more.url) && (
        <a
          href={more.url}
          target="_blank"
          rel="noopener"
          onClick={() => trackAssistantClick("more", more.url)}
          className="inline-block px-1 text-xs text-brand hover:underline"
        >
          See all {more.total} results →
        </a>
      )}
    </div>
  );
}
