import "server-only";

import { apiFetch, NO_CACHE } from "./client";
import type {
  AdminOrder,
  AdminStats,
  AuditLogEntry,
  Order,
  OrderStatus,
  OrderStatusCounts,
  Page,
  Product,
  ProductStatusFilter,
  SortOption,
} from "./types";

// The Phase 0 endpoints (G1-G6). Admin pages are per-user and permission-gated, so nothing
// here is ever cached.

export function getDashboard(token: string) {
  return apiFetch<AdminStats>("/admin/dashboard", { token, cache: NO_CACHE });
}

export function listAdminOrders(
  token: string,
  params: { status?: OrderStatus; page?: number; page_size?: number } = {},
) {
  return apiFetch<Page<AdminOrder>>("/admin/orders", {
    token,
    query: { ...params },
    cache: NO_CACHE,
  });
}

export function getOrderStatusCounts(token: string) {
  return apiFetch<OrderStatusCounts>("/admin/orders/status-counts", { token, cache: NO_CACHE });
}

export function listAudit(token: string, params: { page?: number; page_size?: number } = {}) {
  return apiFetch<Page<AuditLogEntry>>("/admin/audit", {
    token,
    query: { ...params },
    cache: NO_CACHE,
  });
}

export function listAdminProducts(
  token: string,
  params: {
    q?: string;
    category?: string;
    status?: ProductStatusFilter;
    sort?: SortOption;
    page?: number;
    page_size?: number;
  } = {},
) {
  return apiFetch<Page<Product>>("/admin/products", {
    token,
    query: { ...params },
    cache: NO_CACHE,
  });
}

/** Unlike the public product endpoint, this resolves archived products for the edit form. */
export function getAdminProduct(token: string, productId: number) {
  return apiFetch<Product>(`/admin/products/${productId}`, { token, cache: NO_CACHE });
}

export interface ProductInput {
  name: string;
  description: string;
  origin?: string | null;
  price: string;
  stock: number;
  category_id: number;
  image_url?: string | null;
}

export function createProduct(token: string, body: ProductInput) {
  return apiFetch<Product>("/admin/products", {
    method: "POST",
    token,
    body,
    cache: NO_CACHE,
  });
}

export function updateProduct(
  token: string,
  productId: number,
  body: Partial<Omit<ProductInput, "stock">>,
) {
  return apiFetch<Product>(`/admin/products/${productId}`, {
    method: "PATCH",
    token,
    body,
    cache: NO_CACHE,
  });
}

export function setProductArchived(token: string, productId: number, archived: boolean) {
  const action = archived ? "archive" : "unarchive";
  return apiFetch<Product>(`/admin/products/${productId}/${action}`, {
    method: "POST",
    token,
    cache: NO_CACHE,
  });
}

export function adjustStock(token: string, productId: number, delta: number) {
  return apiFetch<Product>(`/admin/products/${productId}/stock`, {
    method: "PATCH",
    token,
    body: { delta },
    cache: NO_CACHE,
  });
}

export function advanceOrderStatus(token: string, orderId: number) {
  return apiFetch<Order>(`/admin/orders/${orderId}/advance-status`, {
    method: "POST",
    token,
    cache: NO_CACHE,
  });
}
