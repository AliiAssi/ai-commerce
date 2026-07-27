import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CartItems } from "@/components/cart/cart-items";
import { getCart } from "@/lib/api/cart";
import { getToken } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Your cart" };

// Per-user, so never cached. Reading the cookie already opts this route out of prerendering.
export const dynamic = "force-dynamic";

export default async function CartPage() {
  const token = await getToken();
  if (!token) redirect("/login?next=/cart");

  const cart = await getCart(token);

  return (
    <>
      <h1 className="mb-6 text-2xl font-bold">Your cart</h1>
      <CartItems initialCart={cart} />
    </>
  );
}
