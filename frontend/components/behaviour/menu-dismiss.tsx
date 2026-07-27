"use client";

import { useEffect } from "react";

// Ported from app.js: a click outside or Escape closes every open <details class="menu">.
// Keeping <details> rather than rebuilding the menus as controlled React means the mobile
// nav and account dropdown still work with JS disabled, exactly as they do today.
export function MenuDismiss() {
  useEffect(() => {
    const closeAll = (except?: Element | null) => {
      document.querySelectorAll<HTMLDetailsElement>("details.menu[open]").forEach((el) => {
        if (el !== except) el.open = false;
      });
    };

    const onClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      closeAll(target?.closest("details.menu"));
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAll();
    };

    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return null;
}
