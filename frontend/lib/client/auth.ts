"use client";

import { clearSessionCache, loadSession } from "./session-store";

interface AuthResult {
  ok: boolean;
  error?: string;
}

async function post(path: string, body?: unknown): Promise<AuthResult> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    return { ok: false, error: "Could not reach the store. Check your connection." };
  }

  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      if (payload.error?.message) message = payload.error.message;
    } catch {
      // a non-JSON error body (a proxy error page) keeps the generic message
    }
    return { ok: false, error: message };
  }

  // the cookie changed, so the cached session is now wrong until this resolves
  await loadSession();
  return { ok: true };
}

export function login(email: string, password: string): Promise<AuthResult> {
  return post("/api/auth/login", { email, password });
}

export function register(email: string, password: string): Promise<AuthResult> {
  return post("/api/auth/register", { email, password });
}

export async function logout(): Promise<AuthResult> {
  clearSessionCache();
  return post("/api/auth/logout");
}
