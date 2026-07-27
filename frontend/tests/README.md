# Frontend tests

Laid out to match `web/tests/` and `ai/tests/`, so the whole repo answers "where are the
tests?" the same way: one `tests/` directory per service, split by kind.

| Directory  | Runner                          | Talks to                                              |
| ---------- | ------------------------------- | ----------------------------------------------------- |
| `unit/`    | Vitest + Testing Library        | nothing — `fetch` is stubbed, no network, no database |
| `e2e/`     | Playwright (arrives in Phase 3) | a real browser against a running `frontend/` + `web/` |
| `support/` | —                               | shared fixtures and module stubs                      |

`unit/` mirrors the source tree: `tests/unit/lib/api/client.test.ts` tests `lib/api/client.ts`.
Tests import through the `@/` alias rather than relative paths, so moving a test does not
rewrite its imports.

`support/server-only.ts` exists because `lib/api/*` imports the real `server-only` package,
which throws by design outside a React Server Component render. Vitest aliases it to the stub.

## Running

```bash
npm run test          # once
npm run test:watch    # watch mode
```

CI runs `npm run test` with no backend — that is deliberate, and why `unit/` may not reach the
network. The `next build` step in the same job is what exercises the real API.
