"use client";

import { useSyncExternalStore } from "react";

import type { User } from "@/lib/api/types";

export interface SessionSnapshot {
  user: User | null;
  cartQuantity: number;
  /** False only before the first snapshot exists at all — see CACHE_KEY below. */
  loaded: boolean;
}

/**
 * The session is external state: it lives in an httpOnly cookie the client cannot read, is
 * shared by the header, the bag controls and the review form, and changes from outside React
 * (logging in, adding to the bag). Modelling it as a module store read through
 * useSyncExternalStore is both the honest description and what keeps the fetch out of an
 * effect body — which would otherwise cascade renders on every mount.
 */
const EMPTY: SessionSnapshot = { user: null, cartQuantity: 0, loaded: false };

/**
 * The last known session, mirrored into localStorage.
 *
 * The storefront's pages are prerendered, so their HTML is identical for every visitor and
 * cannot contain your account menu. Without this the header had to wait for /api/session, and
 * a logged-in visitor watched their own menu appear a beat after the page did.
 *
 * This is display state only, never a credential. The token stays in the httpOnly cookie, and
 * every protected route and API call re-checks it server-side — so the worst case, showing
 * account chrome for the moment after a cookie has expired, costs a redirect to /login and
 * nothing else. loadSession() reconciles it on every page load regardless.
 */
const CACHE_KEY = "beit_session_hint";

function readCache(): SessionSnapshot | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { user: User | null; cartQuantity: number };
    // a hand-edited or half-written entry must not take the header down
    if (typeof parsed !== "object" || parsed === null) return null;
    return {
      user: parsed.user ?? null,
      cartQuantity: typeof parsed.cartQuantity === "number" ? parsed.cartQuantity : 0,
      loaded: true,
    };
  } catch {
    return null;
  }
}

function writeCache(next: SessionSnapshot): void {
  try {
    if (!next.user) localStorage.removeItem(CACHE_KEY);
    else
      localStorage.setItem(
        CACHE_KEY,
        JSON.stringify({ user: next.user, cartQuantity: next.cartQuantity }),
      );
  } catch {
    // private browsing; the header just goes back to waiting for the network
  }
}

// Seeded synchronously at module load, so the first client render after hydration is already
// correct rather than waiting a network round trip.
let snapshot: SessionSnapshot = typeof window === "undefined" ? EMPTY : (readCache() ?? EMPTY);
let started = false;
const listeners = new Set<() => void>();

function publish(next: SessionSnapshot) {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

export async function loadSession(): Promise<void> {
  try {
    const response = await fetch("/api/session", { cache: "no-store" });
    if (!response.ok) throw new Error("session request failed");
    const data = (await response.json()) as { user: User | null; cartQuantity: number };
    const next = { user: data.user, cartQuantity: data.cartQuantity, loaded: true };
    writeCache(next);
    publish(next);
  } catch {
    // a failed probe means "unknown", not "signed out" — keep the cached view rather than
    // flashing the visitor to logged-out because one request lost the network
    publish({ ...snapshot, loaded: true });
  }
}

export function setCartQuantity(cartQuantity: number): void {
  const next = { ...snapshot, cartQuantity };
  writeCache(next);
  publish(next);
}

/** Drops the cached hint outright; used by logout so no stale chrome survives. */
export function clearSessionCache(): void {
  writeCache(EMPTY);
  publish({ ...EMPTY, loaded: true });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // the first component to need the session is what triggers the reconciling fetch
  if (!started) {
    started = true;
    void loadSession();
  }
  return () => {
    listeners.delete(listener);
  };
}

// getSnapshot must be referentially stable between changes, which is why publish() replaces
// the object rather than mutating it.
function getSnapshot(): SessionSnapshot {
  return snapshot;
}

// The server cannot know who is asking for a prerendered page, so SSR and the hydration pass
// both render the empty state; React re-renders from getSnapshot immediately afterwards.
function getServerSnapshot(): SessionSnapshot {
  return EMPTY;
}

export function useSession(): SessionSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
