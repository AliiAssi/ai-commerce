"use client";

import { useState } from "react";

export const PLACEHOLDER_SRC = "/img/placeholder.svg";

/**
 * The Jinja template used an inline `onerror` attribute to swap in the placeholder when a
 * product's image URL 404s. React needs a real onError handler, which needs a client
 * component — so this is the one leaf of the plate that ships JS.
 *
 * Deliberately a plain <img>, not next/image: product image URLs are arbitrary and
 * operator-supplied, so they cannot be enumerated in images.remotePatterns, and the
 * optimiser would reject anything not listed.
 */
export function ProductImage({
  src,
  alt,
  className,
}: {
  src: string | null;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = failed || !src ? PLACEHOLDER_SRC : src;

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={resolved}
      alt={alt}
      loading="lazy"
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
