import { listAllProducts, listCategories } from "@/lib/api/catalog";
import type { Category, Product } from "@/lib/api/types";
import { llmsText } from "@/lib/llms";

export const revalidate = 3600;

export async function GET() {
  let categories: Category[] = [];
  let products: Product[] = [];
  try {
    [categories, products] = await Promise.all([listCategories(), listAllProducts()]);
  } catch {
    // the backend is unreachable: still describe the store and its pages
  }

  return new Response(llmsText(categories, products), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
