export function reviewerName(email: string): string {
  const local = email.split("@")[0] ?? "";
  if (!local) return "A verified buyer";

  const words = local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1));

  if (words.length === 0) return "A verified buyer";
  const [first, ...rest] = words;
  return rest.length > 0 ? `${first} ${rest[rest.length - 1].charAt(0)}.` : first;
}
