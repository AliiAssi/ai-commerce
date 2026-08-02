export function isPendingHref(pendingHref: string | null, linkHref: string): boolean {
  return pendingHref !== null && pendingHref === linkHref;
}

export function optimisticParam(
  pendingHref: string | null,
  current: string,
  name: string,
): string {
  if (pendingHref === null) return current;
  const mark = pendingHref.indexOf("?");
  const query = new URLSearchParams(mark === -1 ? "" : pendingHref.slice(mark + 1));
  return query.get(name) ?? "";
}
