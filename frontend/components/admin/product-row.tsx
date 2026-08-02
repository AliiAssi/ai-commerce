"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { useToast } from "@/components/providers/toast-provider";
import { Badge, StockBadge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { Price } from "@/components/ui/price";
import { ProductImage } from "@/components/ui/product-image";
import { FLASH_MS, useTransient } from "@/lib/client/use-transient";
import { adjustStock, setArchived } from "@/lib/actions/admin";
import type { Product } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/**
 * Replaces partials/admin/product_row.html. HTMX swapped the whole <tr> with server-rendered
 * markup; here the action returns the updated product and the row re-renders from it, so the
 * table stays put and only this row changes — the same effect without a swap target.
 */
export function ProductRow({ product: initial }: { product: Product }) {
  const [product, setProduct] = useState(initial);
  const [changed, flash] = useTransient(FLASH_MS);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  // The row rewrites itself with the server's product, so the new value is the confirmation.
  // Only failures still need the global channel.
  const mutate = (work: () => Promise<{ ok: boolean; data?: Product; error?: string }>) => {
    startTransition(async () => {
      const result = await work();
      if (result.ok && result.data) {
        setProduct(result.data);
        flash();
      } else {
        toast(result.error ?? "That didn't work", "danger");
      }
    });
  };

  const step = (delta: number) => mutate(() => adjustStock(product.id, delta));

  const toggleArchived = () => mutate(() => setArchived(product.id, !product.is_archived));

  const stepClass =
    "h-7 w-7 rounded-el border border-border text-ink-muted hover:border-brand hover:text-brand disabled:opacity-40";

  return (
    <tr className={cn(product.is_archived && "opacity-60", changed && "flash")}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <ProductImage
            src={product.image_url}
            alt=""
            className="h-10 w-10 rounded-el bg-surface-alt object-cover"
          />
          <div className="min-w-0">
            <Link
              href={`/admin/products/${product.id}/edit`}
              className="block truncate font-medium hover:text-brand"
            >
              {product.name}
            </Link>
            <span className="text-xs text-ink-faint">
              #{product.id} &middot; {product.category_name}
            </span>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <Price value={product.price} size="sm" />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => step(-1)}
            disabled={pending || product.stock === 0}
            aria-label={`Decrease stock of ${product.name}`}
            className={stepClass}
          >
            &minus;
          </button>
          <span className="w-10 text-center text-sm font-medium">{product.stock}</span>
          <button
            type="button"
            onClick={() => step(1)}
            disabled={pending}
            aria-label={`Increase stock of ${product.name}`}
            className={stepClass}
          >
            +
          </button>
          <StockBadge stock={product.stock} />
        </div>
      </td>
      <td className="px-4 py-3">
        {product.is_archived ? (
          <Badge variant="warning">Archived</Badge>
        ) : (
          <Badge variant="success">Active</Badge>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-2">
          <LinkButton href={`/admin/products/${product.id}/edit`} variant="secondary" size="sm">
            Edit
          </LinkButton>
          <Button
            type="button"
            variant={product.is_archived ? "ghost" : "danger-outline"}
            size="sm"
            onClick={toggleArchived}
            disabled={pending}
          >
            {product.is_archived ? "Unarchive" : "Archive"}
          </Button>
        </div>
      </td>
    </tr>
  );
}
