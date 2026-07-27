"use server";

import { redirect } from "next/navigation";

import { login, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { safeNext } from "@/lib/auth/redirect";
import { clearSession, setSession } from "@/lib/auth/session";

export interface AuthFormState {
  error?: string;
}

// Shared by both forms. The BFF route handlers in app/api/auth/* stay as the documented
// programmatic surface; both call the same lib/api + session helpers, so there is one
// implementation of "log in and set the cookie", not two.
async function authenticate(
  mode: "login" | "register",
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const next = safeNext(String(formData.get("next") ?? "/"));

  if (!email || !password) {
    return { error: "Email and password are required" };
  }

  try {
    const token =
      mode === "login" ? await login(email, password) : await register(email, password);
    await setSession(token);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  redirect(next);
}

export async function loginAction(
  _prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  return authenticate("login", formData);
}

export async function registerAction(
  _prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  return authenticate("register", formData);
}

export async function logoutAction() {
  await clearSession();
  redirect("/");
}
