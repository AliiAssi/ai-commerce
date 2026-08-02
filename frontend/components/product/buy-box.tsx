"use client";

import { useEffect, useRef, useState } from "react";

import { AddToBagForm, BarAdd } from "@/components/cart/add-to-bag";
import { LOW_STOCK_AT } from "@/components/ui/badge";
import { Price } from "@/components/ui/price";
import { Eyebrow } from "@/components/ui/typography";
import type { Money } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * Price, stock and Add as one block instead of three loose siblings, plus a bar that takes
 * over on a phone once the block itself has scrolled away — otherwise the description and
 * reviews leave no way to buy without scrolling back up.
 */
export function BuyBox({
  productId,
  name,
  price,
  stock,
}: {
  productId: number;
  name: string;
  price: Money;
  stock: number;
}) {
  const anchor = useRef<HTMLDivElement>(null);
  const [passed, setPassed] = useState(false);

  useEffect(() => {
    const element = anchor.current;
    if (!element || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(([entry]) => setPassed(!entry.isIntersecting));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <div
        ref={anchor}
        data-testid="buy-box"
        className="flex flex-col gap-4 rounded-card border border-border bg-surface p-5 shadow-card"
      >
        <div className="flex items-baseline justify-between gap-4">
          <Price value={price} size="xl" />
          {stock > 0 && stock <= LOW_STOCK_AT && <Eyebrow>Only {stock} left</Eyebrow>}
        </div>

        {stock > 0 ? (
          <AddToBagForm productId={productId} stock={stock} />
        ) : (
          <p className="text-sm text-danger">Sold out, check back soon.</p>
        )}
      </div>

      {stock > 0 && (
        <div
          data-testid="buy-bar"
          aria-hidden={!passed}
          className={cn(
            "fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur transition-transform duration-base lg:hidden",
            passed ? "translate-y-0" : "translate-y-full",
          )}
        >
          <div className="mx-auto flex w-full max-w-shell items-center gap-4 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{name}</p>
              <Price value={price} size="sm" />
            </div>
            {/* Kept out of the tab order while off-screen; the real form is still up the page. */}
            <div className={cn(!passed && "invisible")}>
              <BarAdd productId={productId} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
