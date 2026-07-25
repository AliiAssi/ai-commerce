(function () {
  const widget = document.getElementById("chat-widget");
  if (!widget) return;

  const panel = document.getElementById("chat-panel");
  const launcher = document.getElementById("chat-launcher");
  const closeBtn = document.getElementById("chat-close");
  const resetBtn = document.getElementById("chat-reset");
  const messages = document.getElementById("chat-messages");
  const emptyState = document.getElementById("chat-empty");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");

  const SESSION_KEY = "ai_chat_session";
  const USER_KEY = "ai_chat_user";
  const TOOL_LABELS = {
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

  let streaming = false;
  let controller = null;

  // A stale session id from a different logged-in user must not be reused (order scoping).
  const currentUser = document.body.dataset.user || "";
  if (localStorage.getItem(USER_KEY) !== currentUser) {
    localStorage.removeItem(SESSION_KEY);
    localStorage.setItem(USER_KEY, currentUser);
  }

  function openPanel() {
    widget.classList.add("is-open");
    launcher.setAttribute("aria-expanded", "true");
    setTimeout(() => input.focus(), 50);
  }
  function closePanel() {
    widget.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }
  launcher.addEventListener("click", openPanel);
  document.querySelectorAll("[data-chat-open]").forEach((el) =>
    el.addEventListener("click", openPanel)
  );
  closeBtn.addEventListener("click", closePanel);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && widget.classList.contains("is-open")) closePanel();
  });

  resetBtn.addEventListener("click", () => {
    if (controller) controller.abort();
    localStorage.removeItem(SESSION_KEY);
    messages.querySelectorAll("[data-msg]").forEach((el) => el.remove());
    if (emptyState) emptyState.classList.remove("hidden");
    setStreaming(false);
    input.focus();
  });

  function autogrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 128) + "px";
    sendBtn.disabled = streaming || input.value.trim() === "";
  }
  input.addEventListener("input", autogrow);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  widget.querySelectorAll("[data-prompt]").forEach((chip) => {
    chip.addEventListener("click", () => {
      input.value = chip.dataset.prompt;
      autogrow();
      form.requestSubmit();
    });
  });

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
  // minimal, XSS-safe formatting: escape first, then bold / italics / line breaks
  function format(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, "$1<em>$2</em>")
      .replace(/\n/g, "<br>");
  }
  let purifyHooked = false;
  function renderMarkdown(text) {
    if (!window.marked || !window.DOMPurify) return format(text);
    if (!purifyHooked) {
      purifyHooked = true;
      DOMPurify.addHook("afterSanitizeAttributes", (node) => {
        if (node.tagName === "A") {
          node.setAttribute("target", "_blank");
          node.setAttribute("rel", "noopener noreferrer");
        }
      });
    }
    return DOMPurify.sanitize(marked.parse(text, { gfm: true, breaks: true }));
  }
  function scrollDown() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addBubble(role, html) {
    if (emptyState) emptyState.classList.add("hidden");
    const wrap = document.createElement("div");
    wrap.dataset.msg = role;
    wrap.className = "flex " + (role === "user" ? "justify-end" : "justify-start");
    const bubble = document.createElement("div");
    bubble.className =
      "max-w-[80%] break-words rounded-card px-3 py-2 text-sm " +
      (role === "user"
        ? "whitespace-pre-wrap bg-brand text-brand-contrast"
        : "chat-md bg-surface text-ink border border-border shadow-card");
    bubble.innerHTML = html;
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    scrollDown();
    return bubble;
  }

  function typingBubble() {
    const bubble = addBubble("assistant", '<span class="chat-typing"><span></span><span></span><span></span></span>');
    bubble.dataset.typing = "1";
    return bubble;
  }

  function setStreaming(on) {
    streaming = on;
    input.disabled = on;
    sendBtn.disabled = on || input.value.trim() === "";
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message || streaming) return;

    addBubble("user", escapeHtml(message));
    input.value = "";
    autogrow();
    setStreaming(true);
    send(message);
  });

  async function send(message) {
    const bubble = typingBubble();
    let toolNote = null;
    let answer = "";
    let started = false;
    controller = new AbortController();

    const payload = { message: message };
    const sessionId = localStorage.getItem(SESSION_KEY);
    if (sessionId) payload.session_id = sessionId;

    try {
      const resp = await fetch("/api/v1/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
        signal: controller.signal,
      });

      const sid = resp.headers.get("X-Session-Id");
      if (sid) localStorage.setItem(SESSION_KEY, sid);

      if (!resp.ok || !resp.body) {
        finishError(bubble);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sep;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const line = raw.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let event;
          try {
            event = JSON.parse(line.slice(5).trim());
          } catch (_) {
            continue;
          }

          if (event.type === "tool") {
            if (!started) {
              const label = TOOL_LABELS[event.name] || "Working…";
              if (!toolNote) {
                bubble.innerHTML = '<span class="text-xs italic text-ink-muted"></span>';
                toolNote = bubble.firstChild;
              }
              toolNote.textContent = label;
            }
          } else if (event.type === "token") {
            if (!started) {
              started = true;
              bubble.innerHTML = "";
              bubble.classList.add("chat-caret");
              delete bubble.dataset.typing;
            }
            answer += event.text || "";
            bubble.innerHTML = renderMarkdown(answer);
            bubble.classList.add("chat-caret");
            scrollDown();
          } else if (event.type === "error") {
            finishError(bubble, event.message);
            return;
          } else if (event.type === "done") {
            break;
          }
        }
      }

      if (!started && !answer) {
        finishError(bubble);
      } else {
        bubble.classList.remove("chat-caret");
        bubble.innerHTML = renderMarkdown(answer);
      }
    } catch (err) {
      if (err && err.name === "AbortError") {
        bubble.closest("[data-msg]").remove();
      } else {
        finishError(bubble);
      }
    } finally {
      controller = null;
      setStreaming(false);
      scrollDown();
    }
  }

  function finishError(bubble, message) {
    bubble.classList.remove("chat-caret");
    delete bubble.dataset.typing;
    bubble.className =
      "max-w-[80%] rounded-card border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger";
    bubble.textContent =
      message || "The assistant is unavailable right now — please try again in a moment.";
    scrollDown();
  }
})();
