"use client";

import Image from "next/image";
import { useState } from "react";

import { cn } from "@/lib/cn";

export const PLACEHOLDER_SRC = "/img/placeholder.svg";

export function ProductImage({
  src,
  alt,
  className,
  sizes = "100vw",
  priority = false,
}: {
  src: string | null;
  alt: string;
  className?: string;
  sizes?: string;
  /** Set on the one image that is the page's LCP. Everything else stays lazy. */
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = failed || !src ? PLACEHOLDER_SRC : src;

  return (
    <Image
      src={resolved}
      alt={alt}
      fill
      sizes={sizes}
      priority={priority}
      className={cn("object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}

/** The fixed-size thumbnail used by cart, checkout and the admin tables. */
export function ProductThumb({
  src,
  alt,
  size,
  className,
}: {
  src: string | null;
  alt: string;
  size: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = failed || !src ? PLACEHOLDER_SRC : src;

  return (
    <Image
      src={resolved}
      alt={alt}
      width={size}
      height={size}
      className={cn("object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}
