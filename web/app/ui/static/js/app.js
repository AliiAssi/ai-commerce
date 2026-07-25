
(function theme() {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) return;
  const prefersDark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const current = () =>
    document.documentElement.dataset.theme || (prefersDark() ? "dark" : "light");

  function sync() {
    const dark = current() === "dark";
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  }

  toggle.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (_) {}
    sync();
  });
  sync();
})();

// Account menu and mobile nav (both <details class="menu">) close on outside click/Escape.
document.addEventListener("click", (event) => {
  document.querySelectorAll("details.menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("details.menu[open]").forEach((menu) => menu.removeAttribute("open"));
});

// Reveals each element once, staggered, then stops observing it so scrolling back up
// stays calm. Called again after htmx swaps so newly arrived plates animate too.
function revealAll(root) {
  const targets = (root || document).querySelectorAll(".reveal:not(.in)");
  if (!targets.length) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const siblings = [...entry.target.parentElement.children];
        entry.target.style.transitionDelay = Math.min(siblings.indexOf(entry.target), 8) * 55 + "ms";
        entry.target.classList.add("in");
        io.unobserve(entry.target);
      });
    },
    { rootMargin: "0px 0px -12% 0px" }
  );
  targets.forEach((el) => io.observe(el));
}

document.addEventListener("DOMContentLoaded", () => revealAll(document));
document.body.addEventListener("htmx:afterSwap", (event) => revealAll(event.target));

function armToast(el) {
  if (el.dataset.armed) return;
  el.dataset.armed = "1";
  setTimeout(() => {
    el.classList.add("toast-out");
    setTimeout(() => el.remove(), 260);
  }, 4200);
}

function armToasts(root) {
  (root || document).querySelectorAll(".toast").forEach(armToast);
}

document.addEventListener("DOMContentLoaded", () => armToasts(document));

document.body.addEventListener("htmx:afterSwap", () => armToasts(document));
document.body.addEventListener("htmx:oobAfterSwap", () => armToasts(document));

// htmx error responses carry a rendered toast fragment as their body; show it directly,
// or fall back to a generic message if the server couldn't render one (e.g. a 500).
document.body.addEventListener("htmx:responseError", (event) => {
  const toasts = document.getElementById("toasts");
  if (!toasts) return;
  const body = event.detail.xhr.responseText || "";
  if (body.includes("data-toast")) {
    toasts.insertAdjacentHTML("beforeend", body);
  } else {
    toasts.insertAdjacentHTML(
      "beforeend",
      '<div class="toast rounded-el border border-danger bg-danger-subtle text-danger px-4 py-3 text-sm" data-toast>Something went wrong</div>'
    );
  }
  armToasts(toasts);
});
