"use client";

import { useSyncExternalStore } from "react";

import type { User } from "@/lib/api/types";

export interface SessionSnapshot {
  user: User | null;
  cartQuantity: number;
  /** Loading is distinct from signed-out, so the header stays quiet rather than flickering. */
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
const SERVER: SessionSnapshot = EMPTY;

let snapshot: SessionSnapshot = EMPTY;
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
    publish({ user: data.user, cartQuantity: data.cartQuantity, loaded: true });
  } catch {
    publish({ ...EMPTY, loaded: true });
  }
}

export function setCartQuantity(cartQuantity: number): void {
  publish({ ...snapshot, cartQuantity });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // the first component to need the session is what triggers the one fetch
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

function getServerSnapshot(): SessionSnapshot {
  return SERVER;
}

export function useSession(): SessionSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
