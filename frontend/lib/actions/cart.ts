"use server";

import { revalidatePath } from "next/cache";

import { addCartItem, getCart, removeCartItem, updateCartItem } from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";
import type { Cart } from "@/lib/api/types";
import { getToken } from "@/lib/auth/session";
import { failure, type ActionResult } from "./result";

const SIGNED_OUT = { ok: false as const, error: "Log in to use your bag" };

async function withToken(run: (token: string) => Promise<Cart>): Promise<ActionResult<Cart>> {
  const token = await getToken();
  if (!token) return SIGNED_OUT;
  try {
    const cart = await run(token);
    // /cart renders from the server, so it has to be told the numbers moved
    revalidatePath("/cart");
    return { ok: true, data: cart };
  } catch (error) {
    if (error instanceof ApiError) return failure(error);
    throw error;
  }
}

export async function addToBag(productId: number, quantity = 1) {
  return withToken((token) => addCartItem(token, productId, quantity));
}

export async function setQuantity(productId: number, quantity: number) {
  return withToken((token) => updateCartItem(token, productId, quantity));
}

export async function removeFromBag(productId: number) {
  return withToken((token) => removeCartItem(token, productId));
}

/** Used by the cart page to reconcile after an optimistic update is rejected. */
export async function readCart(): Promise<ActionResult<Cart>> {
  return withToken((token) => getCart(token));
}
