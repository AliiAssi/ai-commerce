import { QuickAdd } from "@/components/cart/add-to-bag";
import { Plate } from "@/components/ui/plate";
import { listProducts } from "@/lib/api/catalog";

const SHOWN = 4;

/** Keeps the shelf going instead of ending the page. Same cached listing the catalog uses. */
export async function RelatedProducts({
  categorySlug,
  categoryName,
  excludeId,
}: {
  categorySlug: string;
  categoryName: string;
  excludeId: number;
}) {
  // One extra, so removing the product being viewed still leaves a full row.
  const result = await listProducts({
    category: categorySlug,
    in_stock_only: true,
    page_size: SHOWN + 1,
  });
  const items = result.items.filter((product) => product.id !== excludeId).slice(0, SHOWN);
  if (items.length === 0) return null;

  return (
    <section className="mt-20" data-testid="related-products">
      <div className="mb-8 flex items-baseline justify-between gap-6 border-b border-border pb-5">
        <h2 className="font-serif text-2xl">More from {categoryName}</h2>
        <a
          href={`/catalog?category=${categorySlug}`}
          className="text-sm text-ink-muted transition-colors hover:text-brand"
        >
          See all &rarr;
        </a>
      </div>
      <div className="grid grid-cols-2 gap-x-7 gap-y-10 lg:grid-cols-4">
        {items.map((product) => (
          <Plate
            key={product.id}
            product={product}
            quickAdd={<QuickAdd productId={product.id} productName={product.name} />}
          />
        ))}
      </div>
    </section>
  );
}
