"use client";

import { FooterLink } from "@/components/ui/links";
import { useSession } from "@/lib/client/session-store";

/**
 * The Jinja footer switched this column on `user`; a Server Component in a prerendered layout
 * cannot, so it reads the same client session store the header does.
 */
export function FooterAccountLinks() {
  const { user, loaded } = useSession();

  if (loaded && user) {
    return (
      <>
        <FooterLink href="/account/orders">My orders</FooterLink>
        <FooterLink href="/cart">Cart</FooterLink>
        {user.role === "admin" && <FooterLink href="/admin">Admin panel</FooterLink>}
      </>
    );
  }

  return (
    <>
      <FooterLink href="/login">Log in</FooterLink>
      <FooterLink href="/register">Create an account</FooterLink>
      <FooterLink href="/cart">Cart</FooterLink>
    </>
  );
}
