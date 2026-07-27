import { API_BASE_URL } from "@/lib/api/client";

// The cold-start mitigation the migration audit nearly lost. chat.js fires this once when the
// panel first opens so Render has started waking web/ (and through it ai/) before the user
// finishes typing. Fire-and-forget: the caller does not wait, and a failure is not an error.
export async function POST() {
  try {
    await fetch(`${API_BASE_URL}/api/v1/ai/warm`, { method: "POST", cache: "no-store" });
  } catch {
    // a cold backend is exactly when this fails, and exactly when it does not matter
  }
  return new Response(null, { status: 202 });
}
