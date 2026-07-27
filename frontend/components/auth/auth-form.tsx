"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { login, register } from "@/lib/client/auth";

interface Props {
  mode: "login" | "register";
  next: string;
}

export function AuthForm({ mode, next }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const isLogin = mode === "login";

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");

    setError(null);
    startTransition(async () => {
      const result = isLogin ? await login(email, password) : await register(email, password);
      if (!result.ok) {
        setError(result.error ?? "Something went wrong. Please try again.");
        return;
      }
      // the session cache is already refreshed by lib/client/auth; refresh() re-renders the
      // Server Components on the destination so they see the new cookie too
      router.push(next);
      router.refresh();
    });
  };

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 rounded-card border border-border bg-surface p-6 shadow-card"
    >
      <h1 className="text-xl font-bold">{isLogin ? "Log in" : "Create your account"}</h1>

      {error && (
        <p
          role="alert"
          className="rounded-el border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}

      <Field name="email" label="Email" type="email" required autoComplete="email" />
      <Field
        name="password"
        label="Password"
        type="password"
        required
        autoComplete={isLogin ? "current-password" : "new-password"}
        placeholder={isLogin ? undefined : "At least 8 characters"}
        minLength={isLogin ? undefined : 8}
        maxLength={72}
      />

      <Button type="submit" block disabled={pending}>
        {pending ? "One moment…" : isLogin ? "Log in" : "Sign up"}
      </Button>

      <p className="text-center text-sm text-ink-muted">
        {isLogin ? "New here? " : "Already have an account? "}
        <Link
          href={`${isLogin ? "/register" : "/login"}?next=${encodeURIComponent(next)}`}
          className="text-brand hover:underline"
        >
          {isLogin ? "Create an account" : "Log in"}
        </Link>
      </p>
    </form>
  );
}
