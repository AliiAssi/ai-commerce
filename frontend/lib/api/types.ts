// Mirrors web/app/presentation/schemas/*.py. Keep in sync by hand — the API is small and
// stable, and a generator would add a build step for six files' worth of types.
//
// Every Decimal on the Python side serialises to a JSON *string* (pydantic's json mode), so
// prices and ratings are typed `string` here, not `number`. Formatting them is the Price
// component's job; arithmetic on them is a bug.

export type Money = string;

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  product_count: number;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  origin: string | null;
  price: Money;
  stock: number;
  image_url: string | null;
  rating_avg: Money;
  review_count: number;
  is_archived: boolean;
  category_id: number;
  category_name: string;
  category_slug: string;
  created_at: string;
}

export interface CartItem {
  product_id: number;
  product_name: string;
  unit_price: Money;
  quantity: number;
  line_total: Money;
  available_stock: number;
  is_archived: boolean;
  image_url: string | null;
}

export interface Cart {
  id: number;
  items: CartItem[];
  total_quantity: number;
  grand_total: Money;
}

export const ORDER_STATUSES = ["paid", "shipped", "delivered", "cancelled"] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export interface OrderItem {
  product_id: number;
  product_name: string;
  unit_price: Money;
  quantity: number;
  line_total: Money;
}

export interface Order {
  id: number;
  status: OrderStatus;
  total: Money;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

// The admin view of an order. Carries who placed it; the customer-facing Order does not.
export interface AdminOrder extends Order {
  user_id: number;
  user_email: string | null;
}

export interface Review {
  id: number;
  product_id: number;
  user_id: number;
  user_email: string;
  rating: number;
  text: string;
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  role: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface AuditLogEntry {
  id: number;
  admin_id: number;
  admin_email: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface OrderStatusCounts {
  counts: Record<OrderStatus, number>;
  total: number;
}

export interface AdminStats {
  revenue: Money;
  orders_by_status: Record<string, number>;
  orders_total: number;
  product_count: number;
  active_product_count: number;
  customer_count: number;
  low_stock: Product[];
  recent_orders: AdminOrder[];
  recent_activity: AuditLogEntry[];
}

// Every /api/* error shares this envelope, built by web/app/presentation/error_handlers.py.
export interface ErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface ErrorEnvelope {
  error: ErrorBody;
}

export type SortOption = "newest" | "price_asc" | "price_desc" | "rating";

export type ProductStatusFilter = "all" | "active" | "archived" | "low";
