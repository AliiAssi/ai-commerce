"use client";

import Link from "next/link";
import { useActionState } from "react";

import type { AuthFormState } from "@/lib/actions/auth";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

interface Props {
  mode: "login" | "register";
  next: string;
  action: (prev: AuthFormState, formData: FormData) => Promise<AuthFormState>;
}

export function AuthForm({ mode, next, action }: Props) {
  const [state, formAction, pending] = useActionState(action, {});
  const isLogin = mode === "login";

  return (
    <form
      action={formAction}
      className="space-y-4 rounded-card border border-border bg-surface p-6 shadow-card"
    >
      <h1 className="text-xl font-bold">{isLogin ? "Log in" : "Create your account"}</h1>
      <input type="hidden" name="next" value={next} />

      {state.error && (
        <p
          role="alert"
          className="rounded-el border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger"
        >
          {state.error}
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
