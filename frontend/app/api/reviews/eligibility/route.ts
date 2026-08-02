import { getReviewEligibility } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { getToken } from "@/lib/auth/session";

/**
 * The product page is prerendered, so its HTML is the same for everyone and cannot say
 * whether *you* may review. The composer asks here after hydrating, the same way the header
 * resolves the session — the token stays in the httpOnly cookie and is attached server-side.
 */
export async function GET(request: Request) {
  const id = Number(new URL(request.url).searchParams.get("product"));
  if (!Number.isInteger(id) || id <= 0) {
    return Response.json({ error: "product is required" }, { status: 400 });
  }

  const token = await getToken();

  try {
    return Response.json(await getReviewEligibility(id, token));
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) {
      return Response.json({ error: "not found" }, { status: 404 });
    }
    // The composer treats any failure as "cannot review", so a broken answer costs the
    // entry point rather than the page.
    if (error instanceof ApiError) {
      return Response.json({ can_review: false, reason: null, review: null });
    }
    throw error;
  }
}
