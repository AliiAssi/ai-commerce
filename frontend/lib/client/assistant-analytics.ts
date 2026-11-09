"use client";

import { track } from "@vercel/analytics";

export type AssistantLinkKind = "inline" | "card" | "more";

export const ASSISTANT_CLICK_EVENT = "Assistant link click";

export function trackAssistantClick(kind: AssistantLinkKind, href: string) {
  const url = new URL(href, window.location.origin);
  track(ASSISTANT_CLICK_EVENT, { kind, path: url.pathname });
}
