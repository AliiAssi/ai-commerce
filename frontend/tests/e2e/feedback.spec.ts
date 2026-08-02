import { expect, test } from "@playwright/test";

import { addFirstProductToBag, newEmail, register } from "./support";

const toasts = "[data-toast]";

/**
 * The contract this suite protects: a control that can report its own outcome does, and the
 * global toast channel is left for failures that belong to the page. Every assertion here
 * pairs "the feedback appeared where it belongs" with "and not in the corner".
 */
test.describe("feedback lands where the action happened", () => {
  test("adding from the catalog confirms on the control itself", async ({ page }) => {
    await register(page, newEmail("feedback"));
    await page.goto("/catalog");

    const plate = page.locator("article.plate").first();
    const add = plate.getByRole("button", { name: /Add .* to bag/ });
    await plate.hover();
    await add.click();

    await expect(add).toHaveAttribute("data-added", "true");
    await expect(page.locator(toasts)).toHaveCount(0);
  });

  test("a rejected quantity is reported on its own line", async ({ page }) => {
    await register(page, newEmail("feedback"));
    await addFirstProductToBag(page);
    await page.goto("/cart");

    await page.getByLabel(/^Quantity of /).fill("999");

    const lineError = page.getByTestId("cart-line-error");
    await expect(lineError).toBeVisible();
    await expect(lineError).toBeInViewport();
    await expect(page.locator(toasts)).toHaveCount(0);
  });

  test("the toast region is mounted before anything needs announcing", async ({ page }) => {
    await page.goto("/catalog");

    const region = page.locator("#toasts");
    await expect(region).toHaveAttribute("aria-live", "polite");
    await expect(page.locator(toasts)).toHaveCount(0);
  });
});
