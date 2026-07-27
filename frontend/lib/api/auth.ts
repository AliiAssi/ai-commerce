import "server-only";

import { apiFetch, NO_CACHE } from "./client";
import type { TokenResponse, User } from "./types";

export function login(email: string, password: string) {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    cache: NO_CACHE,
  });
}

export function register(email: string, password: string) {
  return apiFetch<TokenResponse>("/auth/register", {
    method: "POST",
    body: { email, password },
    cache: NO_CACHE,
  });
}

export function getMe(token: string) {
  return apiFetch<User>("/me", { token, cache: NO_CACHE });
}
