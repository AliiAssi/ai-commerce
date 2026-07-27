import { ApiError } from "@/lib/api/client";

/**
 * Server Actions return this instead of throwing. A thrown error in an action becomes an
 * opaque digest in production, which is right for a bug but wrong for "you are out of stock"
 * — the user needs to read that one.
 */
export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

export function failure(error: unknown): { ok: false; error: string } {
  if (error instanceof ApiError) return { ok: false, error: error.message };
  throw error; // a real bug: let the error boundary have it
}
