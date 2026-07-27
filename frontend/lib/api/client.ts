import "server-only";

import type { ErrorEnvelope } from "./types";

// Server-side only. API_BASE_URL is deliberately not NEXT_PUBLIC_*: the browser must never
// learn where the FastAPI service lives. Every call goes browser -> Next -> FastAPI.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isNotFound() {
    return this.status === 404;
  }

  get isUnauthorized() {
    return this.status === 401;
  }

  get isForbidden() {
    return this.status === 403;
  }
}

type CachePolicy =
  { mode: "no-store" } | { mode: "revalidate"; seconds: number; tags?: string[] };

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** Bearer token forwarded to FastAPI. Omit for anonymous endpoints. */
  token?: string | null;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  /**
   * Explicit on every call. Next 16 does not cache fetch by default, so anything that should
   * be cached has to say so — and anything per-user must say no-store out loud.
   */
  cache?: CachePolicy;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`/api/v1${path}`, API_BASE_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const body = (value as ErrorEnvelope).error;
  return typeof body === "object" && body !== null && typeof body.code === "string";
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", token, body, query, cache = { mode: "no-store" }, signal } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  const init: RequestInit & { next?: { revalidate?: number; tags?: string[] } } = {
    method,
    headers,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  };

  if (cache.mode === "revalidate") {
    init.cache = "force-cache";
    init.next = { revalidate: cache.seconds, tags: cache.tags };
  } else {
    init.cache = "no-store";
  }

  const response = await fetch(buildUrl(path, query), init);

  if (response.status === 204) return undefined as T;

  const text = await response.text();

  // Not every failure comes from FastAPI. A sleeping Render instance or a gateway timeout
  // answers with an HTML error page, and JSON.parse would throw a SyntaxError that escapes
  // the ApiError contract every caller relies on.
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new ApiError(
          response.status,
          "invalid_response",
          "API returned a malformed body",
        );
      }
    }
  }

  if (!response.ok) {
    if (isErrorEnvelope(payload)) {
      throw new ApiError(
        response.status,
        payload.error.code,
        payload.error.message,
        payload.error.details,
      );
    }
    throw new ApiError(response.status, "http_error", `Request failed (${response.status})`);
  }

  return payload as T;
}

/** Cache policy for the catalog routes: CDN-cached HTML survives a sleeping Render backend. */
export const CATALOG_CACHE: CachePolicy = { mode: "revalidate", seconds: 300 };

/** Anything per-user. Named so a reviewer can see the intent at the call site. */
export const NO_CACHE: CachePolicy = { mode: "no-store" };

export { API_BASE_URL };
