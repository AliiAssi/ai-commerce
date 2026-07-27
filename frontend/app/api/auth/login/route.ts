import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { setSession } from "@/lib/auth/session";

// The BFF hop. The browser posts here; this handler talks to FastAPI, keeps the token in an
// httpOnly cookie, and returns only the user. The access token is never in a response body.
export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json(
      { error: { code: "bad_request", message: "Invalid JSON" } },
      { status: 400 },
    );
  }

  const { email, password } = (payload ?? {}) as { email?: string; password?: string };
  if (typeof email !== "string" || typeof password !== "string") {
    return Response.json(
      { error: { code: "validation_error", message: "Email and password are required" } },
      { status: 422 },
    );
  }

  try {
    const token = await login(email, password);
    await setSession(token);
    return Response.json({ user: token.user });
  } catch (error) {
    if (error instanceof ApiError) {
      return Response.json(
        { error: { code: error.code, message: error.message } },
        { status: error.status },
      );
    }
    throw error;
  }
}
