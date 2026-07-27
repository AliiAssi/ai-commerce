import "server-only";

import { cookies } from "next/headers";

import { getMe } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { TokenResponse, User } from "@/lib/api/types";

export const SESSION_COOKIE = "beit_session";

// The token never reaches the browser: httpOnly means JS cannot read it, so an XSS cannot
// exfiltrate a session. Server Components and Route Handlers read it back and forward it to
// FastAPI as a bearer header.
export async function setSession(token: TokenResponse): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, token.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: token.expires_in,
  });
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

export async function getToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/** The signed-in user, or null. Swallows an expired/invalid token the way get_optional_user does. */
export async function getCurrentUser(): Promise<User | null> {
  const token = await getToken();
  if (!token) return null;
  try {
    return await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && (error.isUnauthorized || error.isForbidden)) return null;
    throw error;
  }
}

/** Same as getToken, but for routes that must not render at all without a session. */
export async function requireToken(): Promise<string> {
  const token = await getToken();
  if (!token) throw new ApiError(401, "not_authenticated", "Not authenticated");
  return token;
}
