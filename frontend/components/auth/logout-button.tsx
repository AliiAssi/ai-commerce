"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { logout } from "@/lib/client/auth";

export function LogoutButton({ className }: { className?: string }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  return (
    <button
      type="button"
      disabled={pending}
      className={className}
      onClick={() =>
        startTransition(async () => {
          await logout();
          router.push("/");
          router.refresh();
        })
      }
    >
      Log out
    </button>
  );
}
