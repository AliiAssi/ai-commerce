import { getCart } from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";
import { getCurrentUser, getToken } from "@/lib/auth/session";

/**
 * One request for both header concerns: who you are, and how full your bag is.
 *
 * The header needs this on every page, but /, /products/[id] and the static pages are
 * prerendered — a layout that read the cookie on the server would force all of them to render
 * per request, giving up the CDN caching that keeps the store fast while Render is asleep. So
 * the header stays static and fills itself in from here after hydration, which is exactly what
 * the Jinja app already did with its hx-get cart badge.
 */
export async function GET() {
  const token = await getToken();
  if (!token) {
    return Response.json({ user: null, cartQuantity: 0 });
  }

  const user = await getCurrentUser();
  if (!user) {
    // expired or revoked token: report signed-out rather than erroring the header
    return Response.json({ user: null, cartQuantity: 0 });
  }

  let cartQuantity = 0;
  try {
    const cart = await getCart(token);
    cartQuantity = cart.total_quantity;
  } catch (error) {
    // a missing cart is not a broken header
    if (!(error instanceof ApiError)) throw error;
  }

  return Response.json({ user, cartQuantity });
}
