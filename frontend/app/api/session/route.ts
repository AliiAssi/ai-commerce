import { getCart } from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";
import { getCurrentUser, getToken } from "@/lib/auth/session";

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
