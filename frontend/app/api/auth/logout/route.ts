import { clearSession } from "@/lib/auth/session";

export async function POST() {
  await clearSession();
  return new Response(null, { status: 204 });
}
