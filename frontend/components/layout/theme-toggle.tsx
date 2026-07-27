"use client";

import { useSyncExternalStore } from "react";

import { Icon } from "@/components/ui/icon";

type Theme = "light" | "dark";

const THEME_EVENT = "beit:themechange";

// The theme lives on <html data-theme>, written by the pre-paint script in app/layout.tsx and
// by this button. That element is an external store, not React state, so it is read through
// useSyncExternalStore — which also keeps the server snapshot explicit instead of syncing it
// in an effect after hydration.
function subscribe(onChange: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener(THEME_EVENT, onChange);
  media.addEventListener("change", onChange);
  return () => {
    window.removeEventListener(THEME_EVENT, onChange);
    media.removeEventListener("change", onChange);
  };
}

function getSnapshot(): Theme {
  const attr = document.documentElement.dataset.theme;
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// The server cannot know the visitor's OS preference, and tokens.css already handles the
// unset case via prefers-color-scheme, so "light" is only the label's starting guess.
function getServerSnapshot(): Theme {
  return "light";
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const isDark = theme === "dark";

  const toggle = () => {
    const next: Theme = isDark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      // private browsing; the choice just will not persist
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={isDark}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="grid h-9 w-9 place-items-center rounded-el text-ink-muted transition-colors hover:text-brand"
    >
      <Icon name="moon" />
    </button>
  );
}
