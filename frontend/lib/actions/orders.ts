"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { cancelOrder, checkout } from "@/lib/api/orders";
import { getToken } from "@/lib/auth/session";
import { failure, type ActionResult } from "./result";

export async function placeOrder(): Promise<ActionResult<never>> {
  const token = await getToken();
  if (!token) redirect("/login?next=/checkout");

  let orderId: number;
  try {
    const order = await checkout(token);
    orderId = order.id;
  } catch (error) {
    if (error instanceof ApiError) return failure(error);
    throw error;
  }

  revalidatePath("/cart");
  revalidatePath("/account/orders");
  // redirect() throws to unwind, so it must sit outside the try that catches ApiError
  redirect(`/checkout/done/${orderId}`);
}

export async function cancel(orderId: number): Promise<ActionResult<null>> {
  const token = await getToken();
  if (!token) return { ok: false, error: "Log in to manage your orders" };

  try {
    await cancelOrder(token, orderId);
  } catch (error) {
    if (error instanceof ApiError) return failure(error);
    throw error;
  }

  revalidatePath("/account/orders");
  revalidatePath(`/account/orders/${orderId}`);
  return { ok: true, data: null };
}
