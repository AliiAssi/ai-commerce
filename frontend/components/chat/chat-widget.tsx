"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { renderMarkdown } from "@/lib/client/markdown";
import { useSession } from "@/lib/client/session-store";
import { createFrameParser } from "@/lib/client/sse";
import { cn } from "@/lib/cn";

const SESSION_KEY = "ai_chat_session";
const USER_KEY = "ai_chat_user";

// A sleeping AI instance needs ~30-60s to boot, so the panel warms it on open and only tells
// the visitor about it if the wait actually becomes noticeable.
const WAKE_NOTICE_MS = 2500;
const WAKE_NOTICE = "Waking the assistant up, this can take up to a minute…";
const GENERIC_ERROR = "The assistant is unavailable right now — please try again in a moment.";
const MAX_INPUT_HEIGHT = 128;

const TOOL_LABELS: Record<string, string> = {
  search_products: "Searching the catalog…",
  get_product: "Looking up product details…",
  list_categories: "Browsing categories…",
  top_rated_products: "Finding top-rated items…",
  low_stock_products: "Checking stock…",
  store_stats: "Checking the store…",
  get_order: "Looking up your order…",
  list_orders: "Finding your orders…",
  get_order_status: "Checking your order status…",
};

type Status = "typing" | "streaming" | "done" | "error";

interface Message {
  id: number;
  role: "user" | "assistant";
  /** user: raw text. assistant: accumulated markdown, or the error text. */
  text: string;
  note?: string;
  status: Status;
}

function readSessionId(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function ChatWidget() {
  const { user, loaded } = useSession();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);

  const nextId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const warmed = useRef(false);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);

  // A stale session id from a different logged-in user must not be reused: sessions are
  // order-scoped on the AI side, so reuse would leak one customer's orders to the next.
  useEffect(() => {
    if (!loaded) return;
    const current = user ? String(user.id) : "";
    try {
      if (localStorage.getItem(USER_KEY) !== current) {
        localStorage.removeItem(SESSION_KEY);
        localStorage.setItem(USER_KEY, current);
      }
    } catch {
      // private browsing; the session simply will not persist
    }
  }, [loaded, user]);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const openPanel = useCallback(() => {
    setOpen(true);
    if (!warmed.current) {
      warmed.current = true;
      // fire-and-forget: keepalive so it survives the navigation that may follow
      fetch("/api/chat/warm", { method: "POST", keepalive: true }).catch(() => {});
    }
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const closePanel = useCallback(() => {
    setOpen(false);
    launcherRef.current?.focus();
  }, []);

  // The home page hero has an "Ask the assistant" button outside this component.
  useEffect(() => {
    const triggers = document.querySelectorAll<HTMLElement>("[data-chat-open]");
    triggers.forEach((el) => el.addEventListener("click", openPanel));
    return () => triggers.forEach((el) => el.removeEventListener("click", openPanel));
  }, [openPanel]);

  const patch = (id: number, changes: Partial<Message>) => {
    setMessages((current) => current.map((m) => (m.id === id ? { ...m, ...changes } : m)));
  };

  const reset = () => {
    controller.current?.abort();
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      /* nothing to clear */
    }
    setMessages([]);
    setStreaming(false);
    inputRef.current?.focus();
  };

  async function send(message: string) {
    const userId = nextId.current++;
    const botId = nextId.current++;
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", text: message, status: "done" },
      { id: botId, role: "assistant", text: "", status: "typing" },
    ]);
    setStreaming(true);

    const abort = new AbortController();
    controller.current = abort;

    let answer = "";
    let started = false;
    let wakeTimer: ReturnType<typeof setTimeout> | null = setTimeout(() => {
      patch(botId, { note: WAKE_NOTICE });
    }, WAKE_NOTICE_MS);
    const clearWake = () => {
      if (wakeTimer) clearTimeout(wakeTimer);
      wakeTimer = null;
    };

    const sessionId = readSessionId();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sessionId ? { message, session_id: sessionId } : { message }),
        signal: abort.signal,
      });

      // The session id travels in a response header, not in the done frame — the payload's
      // session_id is ignored, exactly as the original client did.
      const sid = response.headers.get("X-Session-Id");
      if (sid) {
        try {
          localStorage.setItem(SESSION_KEY, sid);
        } catch {
          /* non-persistent session */
        }
      }

      if (!response.ok || !response.body) {
        patch(botId, { status: "error", text: GENERIC_ERROR, note: undefined });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const parse = createFrameParser();
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;

        for (const frame of parse(decoder.decode(value, { stream: true }))) {
          if (frame.type === "tool") {
            clearWake();
            patch(botId, { note: TOOL_LABELS[frame.name ?? ""] ?? "Working…" });
          } else if (frame.type === "token") {
            if (!started) {
              clearWake();
              started = true;
            }
            answer += frame.text ?? "";
            patch(botId, { status: "streaming", text: answer, note: undefined });
          } else if (frame.type === "error") {
            patch(botId, {
              status: "error",
              text: frame.message || GENERIC_ERROR,
              note: undefined,
            });
            return;
          } else if (frame.type === "done") {
            finished = true;
            break;
          }
        }
      }

      if (!started && !answer) {
        patch(botId, { status: "error", text: GENERIC_ERROR, note: undefined });
      } else {
        patch(botId, { status: "done", text: answer, note: undefined });
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // a reset mid-stream drops the pending exchange rather than showing an error
        setMessages((current) => current.filter((m) => m.id !== botId));
      } else {
        patch(botId, { status: "error", text: GENERIC_ERROR, note: undefined });
      }
    } finally {
      clearWake();
      controller.current = null;
      setStreaming(false);
    }
  }

  const submit = () => {
    const message = input.trim();
    if (!message || streaming) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    void send(message);
  };

  const autogrow = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT)}px`;
  };

  const suggestions = [
    { label: "Best rated", prompt: "What is best rated right now?" },
    { label: "Gift under $50", prompt: "Recommend a gift under $50" },
    ...(user ? [{ label: "Track my order", prompt: "Where is my most recent order?" }] : []),
  ];

  const ask = (prompt: string) => {
    if (streaming) return;
    void send(prompt);
  };

  return (
    <div className="fixed right-4 bottom-4 z-50 sm:right-5 sm:bottom-5">
      {!open && (
        <button
          ref={launcherRef}
          type="button"
          onClick={openPanel}
          aria-expanded={false}
          aria-controls="chat-panel"
          aria-label="Open the store assistant"
          className="block h-14 w-14 overflow-hidden rounded-full bg-brand shadow-pop transition-transform duration-fast hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          {/* the badge artwork is a theme token (--asset-assistant), so it follows the toggle */}
          <span className="block h-full w-full rounded-full bg-assistant bg-cover bg-center" />
        </button>
      )}

      <section
        id="chat-panel"
        role="dialog"
        aria-label="Store assistant"
        className={cn(
          "chat-panel absolute right-0 bottom-0 flex h-[600px] max-h-[calc(100dvh-2rem)] w-[380px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-card border border-border bg-surface shadow-pop transition-all duration-fast max-sm:fixed max-sm:inset-0 max-sm:h-[100dvh] max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:rounded-none",
          open
            ? "pointer-events-auto translate-y-0 opacity-100"
            : "pointer-events-none translate-y-3 opacity-0",
        )}
        aria-hidden={!open}
      >
        <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3">
          <span className="block h-9 w-9 shrink-0 overflow-hidden rounded-full bg-brand">
            <span className="block h-full w-full rounded-full bg-assistant bg-cover bg-center" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 font-serif text-base text-ink">
              BEIT&apos;s Assistant
              <span className="inline-block h-2 w-2 rounded-full bg-success" title="online" />
            </span>
            <span className="block truncate text-xs text-ink-muted">
              Ask about products &amp; orders
            </span>
          </span>
          <button
            type="button"
            onClick={reset}
            aria-label="Start a new chat"
            className="rounded-el p-1.5 text-ink-muted transition-colors hover:bg-surface-alt hover:text-brand"
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 12a9 9 0 1 1 3 6.7L3 16" />
              <path d="M3 21v-5h5" />
            </svg>
          </button>
          <button
            type="button"
            onClick={closePanel}
            aria-label="Close chat"
            className="rounded-el p-1.5 text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink"
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div
          ref={scroller}
          aria-live="polite"
          aria-atomic="false"
          className="flex-1 space-y-3 overflow-y-auto bg-surface-alt px-4 py-4"
        >
          {messages.length === 0 && (
            <div className="space-y-4">
              <div className="rounded-card bg-surface p-4 text-sm text-ink-muted shadow-card">
                <p className="font-serif text-base text-ink">
                  Ask about anything on the shelves.
                </p>
                <p className="mt-1">
                  Comparisons, recommendations, where a product comes from
                  {user ? ", or where your order is" : ""}.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    className="chat-chip"
                    onClick={() => ask(chip.prompt)}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message) =>
            message.role === "user" ? (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[80%] rounded-card bg-brand px-3 py-2 text-sm break-words whitespace-pre-wrap text-brand-contrast">
                  {message.text}
                </div>
              </div>
            ) : (
              <div key={message.id} className="flex justify-start">
                <AssistantBubble message={message} />
              </div>
            ),
          )}
        </div>

        <form
          className="border-t border-border bg-surface px-3 py-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          {loaded && !user && (
            <p className="mb-2 px-1 text-xs text-ink-muted">
              <Link href="/login" className="text-brand hover:underline">
                Log in
              </Link>{" "}
              to ask about your orders.
            </p>
          )}
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              rows={1}
              maxLength={2000}
              enterKeyHint="send"
              placeholder="Ask anything about the store…"
              value={input}
              disabled={streaming}
              onChange={(event) => {
                setInput(event.target.value);
                autogrow(event.target);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              className="max-h-32 flex-1 resize-none rounded-el border border-border bg-surface-alt px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={streaming || input.trim() === ""}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-el bg-brand text-brand-contrast transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              <svg
                className="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />
              </svg>
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function AssistantBubble({ message }: { message: Message }) {
  if (message.status === "error") {
    return (
      <div className="max-w-[80%] rounded-card border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger">
        {message.text}
      </div>
    );
  }

  if (message.status === "typing") {
    return (
      <div className="max-w-[80%] rounded-card border border-border bg-surface px-3 py-2 text-sm text-ink shadow-card">
        {message.note ? (
          <span className="text-xs text-ink-muted italic">{message.note}</span>
        ) : (
          <span className="chat-typing">
            <span />
            <span />
            <span />
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "chat-md max-w-[80%] rounded-card border border-border bg-surface px-3 py-2 text-sm break-words text-ink shadow-card",
        message.status === "streaming" && "chat-caret",
      )}
      // sanitised in renderMarkdown; this is model output, so DOMPurify is load-bearing
      dangerouslySetInnerHTML={{ __html: renderMarkdown(message.text) }}
    />
  );
}
