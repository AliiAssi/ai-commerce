# frontend — storefront UI

Next.js 16 (App Router) + React 19 + Tailwind v4. The entire user interface: storefront,
auth, cart and checkout, account, the admin area, and the assistant widget.

The browser only ever talks to this app. It holds the session in an httpOnly cookie and calls
[`web/`](../web) server-side with a bearer token, so neither the API's address nor the token
ever reaches the client. That is also why there is no CORS configuration anywhere in the repo.

```
browser ──httpOnly cookie──▶ frontend (app/api/*) ──Bearer──▶ web (/api/v1) ──▶ ai (/chat)
```

## Setup

```bash
cd frontend
nvm use                      # Node 20.9+ — the version is pinned in .nvmrc
npm install
cp .env.example .env.local
```

| Variable       | Purpose                                                                           |
| -------------- | --------------------------------------------------------------------------------- |
| `API_BASE_URL` | where `web/` is. **Not** `NEXT_PUBLIC_*` — the browser must never receive it      |
| `AI_ENABLED`   | `false` hides the assistant widget. Read at **build** time for prerendered routes |

## Run

```bash
npm run dev                  # needs web/ running on API_BASE_URL
npm run build && npm run start
```

`next build` prerenders the home page, the static pages and **every product page**, so the API
must be reachable at build time. A build against a dead backend fails loudly rather than
shipping an empty catalog.

## Test & lint

```bash
npm run lint && npm run format:check
npm run typecheck
npm run test                 # Vitest — no backend needed, fetch is stubbed
npm run test:e2e:stack       # Playwright — brings up its own Postgres + API, then tears down
```

All four run in CI. See [tests/README.md](tests/README.md) for the layout and
[tests/e2e/README.md](tests/e2e/README.md) for what the browser tests cover and why.

## Layout

| Path                    | What it is                                                                   |
| ----------------------- | ---------------------------------------------------------------------------- |
| `app/`                  | routes. `app/api/*` are Route Handlers — the endpoints the **browser** calls |
| `lib/api/`              | the server-only client for `web/`; every file opens `import "server-only"`   |
| `lib/client/`           | browser-side state: the session store, SSE frame parsing, markdown           |
| `lib/actions/`          | Server Actions for mutations (cart, orders, reviews, admin)                  |
| `lib/auth/`             | cookie/session helpers and the open-redirect guard                           |
| `components/ui/`        | design primitives, 1:1 with the Jinja app's `primitives.html` macros         |
| `components/behaviour/` | ported vanilla-JS behaviours: scroll reveal, menu dismissal                  |
| `styles/`               | `tokens.css`, ported unchanged, plus the Tailwind `@theme` map               |

Two directories are called `api` and they are opposite ends of one hop: `app/api/` is inbound
(the URL path _is_ the folder path, so the name is fixed by Next), `lib/api/` is outbound. The
`import "server-only"` at the top of every `lib/api/` file is what enforces the boundary — it
is a build error if one of those modules ever reaches a client bundle.

## Rendering

| Route                                                                 | Mode                                                                  |
| --------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `/`, `/about`, `/makers`, `/shipping`                                 | static, 5 min revalidate                                              |
| `/products/[id]`                                                      | SSG via `generateStaticParams`, 5 min revalidate                      |
| `/catalog`                                                            | dynamic — it reads `searchParams`, which is per-request by definition |
| `/cart`, `/checkout`, `/account/*`, `/admin/*`, `/login`, `/register` | dynamic, never cached                                                 |

The prerendered routes are what keep the store usable while Render's free tier is asleep:
CDN-cached HTML is served whether or not the backend is awake, so a cold start degrades data
freshness instead of blocking the page.

Because those pages are shared by every visitor, their HTML cannot contain your account menu.
The header therefore reads the session on the client, seeded synchronously from a cached hint
in `localStorage` so it is correct at hydration rather than a network round trip later. That
hint holds display fields only — never a token — and every route and API call still enforces
auth server-side.

## Design values

Colours, radii, shadows, motion and type all come from `styles/tokens.css`. Never hardcode
one. Light/dark follows the OS unless `data-theme` is set explicitly, and the pre-paint script
in `app/layout.tsx` applies a saved choice before first paint so the page never flashes.

## Working on this

**Next 16 differs from Next 15 in ways that change ordinary code**, and the docs shipped inside
the install (`node_modules/next/dist/docs/`) are the source of truth for this version. The
differences that have already caused real bugs in this codebase:

- `cookies()`, `params` and `searchParams` are **async**.
- `fetch` is **not cached by default**; caching is opt-in per call, which is why
  `lib/api/client.ts` makes every request state its cache policy.
- A `"use client"` module exports **client references, not values** — importing a plain array
  from one into a Server Component typechecks, compiles, and then fails at build.
- `middleware` is now `proxy`, and Turbopack is the default bundler.

One more, from experience rather than the docs: anything that used to rely on a full page load
needs re-checking. The App Router keeps the layout mounted across navigation, and query-string
changes do not alter `usePathname()`. Several bugs here came from exactly that, which is what
`tests/e2e/` exists to catch.
