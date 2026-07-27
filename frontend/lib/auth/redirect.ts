export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next) return fallback;
  const candidate = next.replaceAll("\\", "/");
  if (!candidate.startsWith("/")) return fallback;
  if (candidate.startsWith("//")) return fallback;
  return candidate;
}
