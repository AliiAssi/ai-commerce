"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Matches `--motion-slow`, which is how long the `.flash` animation in app.css runs. */
export const FLASH_MS = 700;

/** A flag that turns itself off, for confirmations that live on the control they belong to. */
export function useTransient(ms = 1600): [boolean, () => void] {
  const [on, setOn] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const trigger = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setOn(true);
    timer.current = setTimeout(() => setOn(false), ms);
  }, [ms]);

  return [on, trigger];
}
