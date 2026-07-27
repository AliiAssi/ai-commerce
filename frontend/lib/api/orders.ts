import "server-only";

import { apiFetch, NO_CACHE } from "./client";
import type { Order } from "./types";

export function checkout(token: string) {
  return apiFetch<Order>("/checkout", { method: "POST", token, cache: NO_CACHE });
}

export function listOrders(token: string) {
  return apiFetch<Order[]>("/orders", { token, cache: NO_CACHE });
}

export function getOrder(token: string, orderId: number) {
  return apiFetch<Order>(`/orders/${orderId}`, { token, cache: NO_CACHE });
}

export function cancelOrder(token: string, orderId: number) {
  return apiFetch<Order>(`/orders/${orderId}/cancel`, {
    method: "POST",
    token,
    cache: NO_CACHE,
  });
}
