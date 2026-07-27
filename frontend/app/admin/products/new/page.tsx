import type { Metadata } from "next";
import Link from "next/link";

import { ProductForm } from "@/components/admin/product-form";
import { createProductAction } from "@/lib/actions/admin";
import { listCategories } from "@/lib/api/catalog";

export const metadata: Metadata = { title: "New product · Admin" };

export default async function NewProductPage() {
  const categories = await listCategories();

  return (
    <div className="mx-auto max-w-2xl">
      <Link href="/admin/products" className="text-sm text-ink-muted hover:text-brand">
        &larr; Products
      </Link>
      <h1 className="mt-2 mb-6 text-2xl font-bold">New product</h1>
      <ProductForm categories={categories} action={createProductAction} />
    </div>
  );
}
