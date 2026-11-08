"use client";

import { useEffect, useRef, useState } from "react";

import { MARK } from "@/components/hero/hero-mark-data";
import { cn } from "@/lib/cn";

type Status = "loading" | "ready" | "fallback";

function StaticMark() {
  const [x0, y0, x1, y1] = MARK.box;
  return (
    <div className="absolute inset-0 flex items-center justify-center xl:justify-end xl:pe-[12%]">
      <svg viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`} className="h-2/5 w-auto fill-brand">
        <path d={MARK.path} />
      </svg>
    </div>
  );
}

/**
 * بيت floating over Lebanon's relief. three.js loads only after hydration; without WebGL, or
 * without JavaScript, the shaped word is drawn as a flat SVG in the same place.
 */
export function HeroMark({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let dispose: (() => void) | null = null;
    let cancelled = false;
    const fallback = () => {
      if (!cancelled) setStatus("fallback");
    };

    import("@/components/hero/lebanon-scene")
      .then(({ mountLebanonScene }) => {
        if (cancelled) return;
        dispose = mountLebanonScene(canvas, {
          onReady: () => setStatus("ready"),
          onError: fallback,
        });
        if (!dispose) fallback();
      })
      .catch(fallback);

    return () => {
      cancelled = true;
      dispose?.();
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none relative select-none", className)}
    >
      <canvas
        ref={canvasRef}
        data-status={status}
        className={cn(
          "block h-full w-full transition-opacity duration-slow",
          status === "ready" ? "opacity-100" : "opacity-0",
        )}
      />
      {status === "fallback" && <StaticMark />}
      <noscript>
        <StaticMark />
      </noscript>
    </div>
  );
}
