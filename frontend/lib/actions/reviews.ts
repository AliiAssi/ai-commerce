"use server";

import { revalidatePath } from "next/cache";

import { createReview } from "@/lib/api/catalog";
import type { Review } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";
import { getToken } from "@/lib/auth/session";
import { failure, type ActionResult } from "./result";

export async function submitReview(
  productId: number,
  rating: number,
  text: string,
): Promise<ActionResult<Review>> {
  const token = await getToken();
  if (!token) return { ok: false, error: "Log in to review this product" };

  let review: Review;
  try {
    review = await createReview(productId, token, { rating, text });
  } catch (error) {
    if (error instanceof ApiError) return failure(error);
    throw error;
  }

  // the product page is ISR-cached, so the new review needs an explicit invalidation
  revalidatePath(`/products/${productId}`);
  return { ok: true, data: review };
}
