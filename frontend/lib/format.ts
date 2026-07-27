// Timestamps arrive as ISO strings. Both formats are pinned to en-US and UTC so a server
// render and a client hydration can never disagree about locale or timezone — a mismatch
// there is a hydration error, not a cosmetic difference.
const DATE = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/** "Jul 26, 2026" — matches strftime("%b %d, %Y") in the Jinja templates. */
export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

/** "Jul 26, 2026 at 14:30" — matches strftime("%b %d, %Y at %H:%M"). */
export function formatDateTime(iso: string): string {
  const parts = DATE_TIME.formatToParts(new Date(iso));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("month")} ${get("day")}, ${get("year")} at ${get("hour")}:${get("minute")}`;
}
