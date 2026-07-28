import { ApiError } from "@/lib/api/client";
import { UNAUTHENTICATED } from "./codes";

/**
 * Server Actions return this instead of throwing. A thrown error in an action becomes an
 * opaque digest in production, which is right for a bug but wrong for "you are out of stock"
 * — the user needs to read that one.
 *
 * `code` lets a caller branch on *why* without matching the message text. The one that
 * matters is `unauthenticated`: the client cannot read the httpOnly session cookie, so only
 * the server can say for certain whether someone is signed in.
 */
export type ActionFailure = { ok: false; error: string; code?: string };

export type ActionResult<T> = { ok: true; data: T } | ActionFailure;

export function failure(error: unknown): ActionFailure {
  if (error instanceof ApiError) {
    return {
      ok: false,
      error: error.message,
      code: error.isUnauthorized ? UNAUTHENTICATED : error.code,
    };
  }
  throw error; // a real bug: let the error boundary have it
}
