// Ported from _safe_next() in web/app/presentation/controllers/pages/auth_controller.py.
// Only same-site relative targets are allowed, to avoid open-redirect abuse. Deleting the
// Jinja page controllers deletes the only copy of this rule, so it has to live here now.
//
// Rejected: absolute URLs ("https://evil.test"), protocol-relative ("//evil.test"), and
// anything not starting with a single "/". Backslashes are stripped first because some
// browsers normalise "/\evil.test" to a protocol-relative URL.
export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next) return fallback;
  const candidate = next.replaceAll("\\", "/");
  if (!candidate.startsWith("/")) return fallback;
  if (candidate.startsWith("//")) return fallback;
  return candidate;
}
