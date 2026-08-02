import { expect, test, type Page } from "@playwright/test";

import { newEmail, register } from "./support";

/**
 * Navigation feedback is by definition transient, so every test here holds the RSC payload
 * open to make the pending window observable. Without the hold these assertions would be a
 * race against a fast local backend.
 */
async function holdNavigation(page: Page, pattern: RegExp, ms = 2000): Promise<void> {
  await page.route(pattern, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, ms));
    await route.continue();
  });
}

const plates = (page: Page) => page.locator("article.plate");
const results = (page: Page) => page.getByTestId("catalog-results");

test.describe("catalog navigation feedback", () => {
  test("a category lights up before its results arrive", async ({ page }) => {
    await page.goto("/catalog");
    await expect(plates(page).first()).toBeVisible();

    await holdNavigation(page, /\/catalog/);

    // nth(0) is "Everything"; the first real category is the one that changes the URL
    const category = page.getByTestId("filters-rail").getByRole("link").nth(1);
    await category.click();

    await expect(category).toHaveAttribute("aria-current", "true");
    await expect(page).not.toHaveURL(/category=/);
  });

  test("the previous results stay on screen, marked busy, while the next load", async ({
    page,
  }) => {
    await page.goto("/catalog");
    await expect(plates(page).first()).toBeVisible();
    const before = await plates(page).count();

    await holdNavigation(page, /\/catalog/);
    await page.getByTestId("filters-rail").getByRole("link").nth(1).click();

    // dimmed, not blanked: the shopper keeps their place
    await expect(results(page)).toHaveAttribute("aria-busy", "true");
    await expect(plates(page)).toHaveCount(before);
    await expect(page.getByTestId("plate-grid-skeleton")).toHaveCount(0);

    await expect(results(page)).not.toHaveAttribute("aria-busy", "true");
  });

  test("changing the sort reports itself instead of doing nothing visible", async ({
    page,
  }) => {
    await page.goto("/catalog");
    await expect(plates(page).first()).toBeVisible();

    await holdNavigation(page, /\/catalog/);
    await page.getByLabel("Sort products").selectOption("price_asc");

    await expect(results(page)).toHaveAttribute("aria-busy", "true");
    await expect(page).toHaveURL(/sort=price_asc/);
  });

  test("turning a page reports itself too", async ({ page }) => {
    await page.goto("/catalog");
    await expect(plates(page).first()).toBeVisible();

    await holdNavigation(page, /\/catalog/);
    await page.getByRole("link", { name: /Next/ }).click();

    await expect(results(page)).toHaveAttribute("aria-busy", "true");
    await expect(page).toHaveURL(/page=2/);
  });
});

/**
 * How long a skeleton stays on screen is deliberately not asserted here. A prefetched route
 * navigates from cache and shows no skeleton at all — the better outcome, and a race no test
 * should depend on. What must hold is that each route ships a loading boundary: the fallback
 * is streamed in the shell ahead of the data, which is what makes it available to the router.
 */
test.describe("route skeletons", () => {
  const cases = [
    { path: "/account/orders", label: "Loading your orders" },
    { path: "/cart", label: "Loading your cart" },
  ];

  for (const { path, label } of cases) {
    test(`${path} streams its skeleton ahead of the data`, async ({ page }) => {
      await register(page, newEmail("loading"));

      const response = await page.goto(path);
      expect(response?.ok()).toBe(true);
      expect(await response!.text()).toContain(label);
    });
  }
});
