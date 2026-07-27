import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthForm } from "@/components/auth/auth-form";
import { registerAction } from "@/lib/actions/auth";
import { safeNext } from "@/lib/auth/redirect";
import { getCurrentUser } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Create account" };

export default async function RegisterPage(props: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await props.searchParams;
  const target = safeNext(Array.isArray(next) ? next[0] : next);

  if (await getCurrentUser()) redirect(target);

  return (
    <div className="mx-auto max-w-sm">
      <AuthForm mode="register" next={target} action={registerAction} />
    </div>
  );
}
