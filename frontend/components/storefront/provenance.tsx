import Link from "next/link";

import { Eyebrow } from "@/components/ui/typography";
import { placeFor, placeSlug } from "@/lib/provenance";

export function Provenance({ origin }: { origin: string | null }) {
  if (!origin) return null;
  const place = placeFor(origin);

  return (
    <section
      className="flex flex-col gap-3 border-t border-border pt-6"
      data-testid="provenance"
    >
      <Eyebrow>From {origin}</Eyebrow>
      {place && (
        <p className="max-w-[52ch] text-sm leading-relaxed text-ink-muted">{place.text}</p>
      )}
      <Link
        href={place ? `/makers#${placeSlug(place.name)}` : "/makers"}
        className="self-start border-b border-border py-0.5 text-sm text-ink transition-colors hover:border-brand hover:text-brand"
      >
        Meet the makers &rarr;
      </Link>
    </section>
  );
}
