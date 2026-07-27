# End-to-end tests

Playwright, driving a real browser against a built `frontend/` and a running `web/` API.

## Running

```bash
npm run test:e2e:stack        # brings up Postgres + API + build, runs the suite, tears down
npm run test:e2e:stack -- --ui
```

The script uses a throwaway Postgres container on port 55450 and an API on 8010, so it can
never touch a development or production database.

If you already have the stack running:

```bash
API_BASE_URL=http://127.0.0.1:8000 npm run test:e2e
```

## What these cover that the unit tests cannot

Every bug that reached the browser during this migration had the same shape: behaviour that
worked under Jinja because every interaction was a full page load, and broke once Next
navigated on the client without rebuilding the document.

| File              | Guards                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth.spec.ts`    | the header updating on login/logout without a reload; the account dropdown closing when an item inside it is chosen; the header surviving a refresh without flashing signed-out; `?next=` refusing off-site targets |
| `catalog.spec.ts` | products staying **visible** after sorting, paging and filtering — all same-pathname navigations that left plates stuck at `.reveal`'s `opacity: 0`                                                                 |
| `shop.spec.ts`    | the bag badge, quantity and removal, checkout, order history and cancellation                                                                                                                                       |

`catalog.spec.ts` asserts visibility rather than presence on purpose: a plate that never
receives `.in` is in the DOM and reads fine in `curl`, but is invisible on the page. That is
exactly the bug the unit tests missed.

## Conventions

- Each test registers its own account (`newEmail()`), so no test depends on another's cart or
  order history and the suite is safe to re-run against the same database.
- `workers: 1` — the suite shares one seeded catalog, and parallel checkouts would contend
  over the same stock.
