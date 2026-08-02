export interface Place {
  /** The heading on /makers, and the anchor it is reachable at. */
  name: string;
  match: readonly string[];
  text: string;
}

export const PLACES: readonly Place[] = [
  {
    name: "Koura, North Lebanon",
    match: ["koura"],
    text: "Olive country. The oil is pressed within hours of picking, from groves some families have held for six generations.",
  },
  {
    name: "Hasbaya & the Bekaa",
    match: ["hasbaya", "bekaa"],
    text: "Za'atar dried on rooftops and milled by hand; mouneh, the pantry put up in season, from farm kitchens in the valley.",
  },
  {
    name: "Tripoli",
    match: ["tripoli"],
    text: "Soap city since the Mamluks. Olive oil soap is still cut by wire and cured nine months in stacked towers before it ships.",
  },
  {
    name: "Beit Chabab",
    match: ["beit chabab"],
    text: "A mountain village that has thrown terracotta from its own red clay for three hundred years. Our pitchers and pots are fired there.",
  },
  {
    name: "Sarafand, South Lebanon",
    match: ["sarafand"],
    text: "One of the last hand-blown glass workshops on the Phoenician coast, turning recycled glass into sea-green tumblers.",
  },
  {
    name: "Bcharre & the Chouf",
    match: ["bcharre", "chouf"],
    text: "Cedar and walnut worked into boards, boxes and backgammon sets in small mountain ateliers.",
  },
  {
    name: "Beirut",
    match: ["beirut"],
    text: "The roasters and confectioners, cardamom coffee ground to order, and sweets that don't survive the week.",
  },
] as const;

export function placeSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * The workshop behind a product's origin, or null when we have not written about that place.
 * Most origins in the catalog have no entry, and a near-miss would put someone else's craft
 * under this product — so an unmatched origin gets no story rather than an invented one.
 */
export function placeFor(origin: string | null | undefined): Place | null {
  if (!origin) return null;
  const needle = origin.toLowerCase();
  return PLACES.find((place) => place.match.some((token) => needle.includes(token))) ?? null;
}
