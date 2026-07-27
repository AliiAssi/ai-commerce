import { API_BASE_URL } from "@/lib/api/client";
import { getToken } from "@/lib/auth/session";

// SSE proxy: browser -> Next -> web/ -> ai/. The response body is piped straight through
// rather than buffered, so tokens still stream one frame at a time. Buffering here would
// turn the whole point of the streaming endpoint into a single delayed blob.
export async function POST(request: Request) {
  const token = await getToken();
  const body = await request.text();

  const upstream = await fetch(`${API_BASE_URL}/api/v1/ai/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body,
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new Response(text || JSON.stringify({ error: { code: "ai_unavailable" } }), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
      "X-Session-Id": upstream.headers.get("X-Session-Id") ?? "",
    },
  });
}
