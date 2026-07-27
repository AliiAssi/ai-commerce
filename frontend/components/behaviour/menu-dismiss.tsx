"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

function closeAll(except?: Element | null) {
  document.querySelectorAll<HTMLDetailsElement>("details.menu[open]").forEach((el) => {
    if (el !== except) el.open = false;
  });
}

export function MenuDismiss() {
  const pathname = usePathname();

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const menu = target?.closest("details.menu");

      // the summary is the toggle; let the browser handle it and only close the others
      if (menu && target?.closest("summary")) {
        closeAll(menu);
        return;
      }

      // an actionable item inside a menu means a choice was made — close it as well
      if (menu && target?.closest("a, button")) {
        closeAll();
        return;
      }

      closeAll(menu);
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

  // Belt and braces for navigation that does not originate from a click inside the menu —
  // a redirect after logging out, say. Guarded against the mount run: closing menus when this
  // first appears is a no-op in the app, but it is not what this is for.
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    closeAll();
  }, [pathname]);

  return null;
}
