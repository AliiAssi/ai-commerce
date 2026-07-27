import "server-only";

import { apiFetch, NO_CACHE } from "./client";
import type { Cart } from "./types";

// Every cart call is per-user, so all of them are no-store.

export function getCart(token: string) {
  return apiFetch<Cart>("/cart", { token, cache: NO_CACHE });
}

export function addCartItem(token: string, productId: number, quantity = 1) {
  return apiFetch<Cart>("/cart/items", {
    method: "POST",
    token,
    body: { product_id: productId, quantity },
    cache: NO_CACHE,
  });
}

export function updateCartItem(token: string, productId: number, quantity: number) {
  return apiFetch<Cart>(`/cart/items/${productId}`, {
    method: "PATCH",
    token,
    body: { quantity },
    cache: NO_CACHE,
  });
}

export function removeCartItem(token: string, productId: number) {
  return apiFetch<Cart>(`/cart/items/${productId}`, {
    method: "DELETE",
    token,
    cache: NO_CACHE,
  });
}
