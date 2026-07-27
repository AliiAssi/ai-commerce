import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProductForm } from "@/components/admin/product-form";
import { updateProductAction } from "@/lib/actions/admin";
import { getAdminProduct } from "@/lib/api/admin";
import { listCategories } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { requireToken } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Edit product · Admin" };

export default async function EditProductPage(props: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await props.params;
  const id = Number.parseInt(idParam, 10);
  if (!Number.isInteger(id) || id <= 0) notFound();

  const token = await requireToken();

  let product;
  try {
    // G6 — unlike the public endpoint, this resolves archived products, which is the whole
    // reason an archived item can still be edited (and then unarchived).
    product = await getAdminProduct(token, id);
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) notFound();
    throw error;
  }

  const categories = await listCategories();
  // the action needs the id, and a Server Action cannot take it from the form alone safely
  const action = updateProductAction.bind(null, id);

  return (
    <div className="mx-auto max-w-2xl">
      <Link href="/admin/products" className="text-sm text-ink-muted hover:text-brand">
        &larr; Products
      </Link>
      <h1 className="mt-2 mb-6 text-2xl font-bold">Edit: {product.name}</h1>
      <ProductForm product={product} categories={categories} action={action} />
    </div>
  );
}
