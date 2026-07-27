"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  adjustStock as apiAdjustStock,
  advanceOrderStatus as apiAdvanceOrderStatus,
  createProduct as apiCreateProduct,
  setProductArchived as apiSetProductArchived,
  updateProduct as apiUpdateProduct,
} from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import type { Order, Product } from "@/lib/api/types";
import { getToken } from "@/lib/auth/session";
import { failure, type ActionResult } from "./result";

const SIGNED_OUT = { ok: false as const, error: "Your admin session has expired" };

async function run<T>(work: (token: string) => Promise<T>): Promise<ActionResult<T>> {
  const token = await getToken();
  if (!token) return SIGNED_OUT;
  try {
    return { ok: true, data: await work(token) };
  } catch (error) {
    if (error instanceof ApiError) return failure(error);
    throw error;
  }
}

// The row components re-render from the returned product, so the table does not need a full
// reload — but the dashboard's counters read the same data, so it is invalidated too.
function revalidateProducts(productId?: number) {
  revalidatePath("/admin/products");
  revalidatePath("/admin");
  revalidatePath("/admin/audit");
  revalidatePath("/catalog");
  if (productId) revalidatePath(`/products/${productId}`);
}

export async function adjustStock(
  productId: number,
  delta: number,
): Promise<ActionResult<Product>> {
  const result = await run((token) => apiAdjustStock(token, productId, delta));
  if (result.ok) revalidateProducts(productId);
  return result;
}

export async function setArchived(
  productId: number,
  archived: boolean,
): Promise<ActionResult<Product>> {
  const result = await run((token) => apiSetProductArchived(token, productId, archived));
  if (result.ok) revalidateProducts(productId);
  return result;
}

export async function advanceOrder(orderId: number): Promise<ActionResult<Order>> {
  const result = await run((token) => apiAdvanceOrderStatus(token, orderId));
  if (result.ok) {
    revalidatePath("/admin/orders");
    revalidatePath("/admin");
    revalidatePath("/admin/audit");
  }
  return result;
}

export interface ProductFormState {
  error?: string;
}

function readProductForm(formData: FormData) {
  const text = (key: string) => String(formData.get(key) ?? "").trim();
  return {
    name: text("name"),
    description: text("description"),
    origin: text("origin") || null,
    price: text("price"),
    image_url: text("image_url") || null,
    category_id: Number(formData.get("category_id")),
    stock: Number(formData.get("stock") ?? 0),
  };
}

export async function createProductAction(
  _prev: ProductFormState,
  formData: FormData,
): Promise<ProductFormState> {
  const input = readProductForm(formData);
  const result = await run((token) => apiCreateProduct(token, input));
  if (!result.ok) return { error: result.error };

  revalidateProducts(result.data.id);
  redirect("/admin/products");
}

export async function updateProductAction(
  productId: number,
  _prev: ProductFormState,
  formData: FormData,
): Promise<ProductFormState> {
  const { name, description, origin, price, image_url, category_id } =
    readProductForm(formData);
  // stock is deliberately not updatable here: it only moves through the audited +/- controls
  // on the product list, so a silent overwrite from an edit form cannot lose a stock change
  const result = await run((token) =>
    apiUpdateProduct(token, productId, {
      name,
      description,
      origin,
      price,
      image_url,
      category_id,
    }),
  );
  if (!result.ok) return { error: result.error };

  revalidateProducts(productId);
  redirect("/admin/products");
}
