import { clearSession } from "@/lib/auth/session";

// No FastAPI call needed: the session lives entirely in this cookie, so dropping it is logout.
export async function POST() {
  await clearSession();
  return new Response(null, { status: 204 });
}
