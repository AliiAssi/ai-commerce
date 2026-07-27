import { expect, test } from "@playwright/test";

import { addFirstProductToBag, cartBadge, newEmail, register } from "./support";

test.describe("cart and checkout", () => {
  test("adding to the bag updates the badge without a reload", async ({ page }) => {
    await register(page, newEmail("bag"));

    const name = await addFirstProductToBag(page);

    await expect(cartBadge(page)).toHaveAccessibleName(/1 item/);

    await page.goto("/cart");
    await expect(page.getByRole("link", { name })).toBeVisible();
  });

  test("changing quantity and removing a line updates the totals", async ({ page }) => {
    await register(page, newEmail("qty"));
    await addFirstProductToBag(page);
    await page.goto("/cart");

    const quantity = page.getByRole("spinbutton", { name: /^Quantity of / });
    await quantity.fill("3");
    await quantity.blur();

    await expect(cartBadge(page)).toHaveAccessibleName(/3 items/);

    await page.getByRole("button", { name: /^Remove / }).click();

    await expect(page.getByText("Your cart is empty")).toBeVisible();
  });

  test("checkout places an order and confirms it", async ({ page }) => {
    await register(page, newEmail("checkout"));
    await addFirstProductToBag(page);

    await page.goto("/checkout");
    await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page).toHaveURL(/\/checkout\/done\/\d+/);
    await expect(page.getByRole("heading", { name: /is confirmed/ })).toBeVisible();
  });

  test("an empty cart cannot reach checkout", async ({ page }) => {
    await register(page, newEmail("empty"));

    await page.goto("/checkout");

    await expect(page).toHaveURL(/\/cart$/);
  });

  test("an order appears in history and can be cancelled", async ({ page }) => {
    await register(page, newEmail("orders"));
    await addFirstProductToBag(page);
    await page.goto("/checkout");
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page).toHaveURL(/\/checkout\/done\/\d+/);

    await page.goto("/account/orders");
    await expect(page.getByText("Paid")).toBeVisible();
    await page
      .getByRole("link", { name: /^Order #/ })
      .first()
      .click();

    await expect(page).toHaveURL(/\/account\/orders\/\d+/);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Cancel order" }).click();

    await expect(page.getByText("Cancelled")).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel order" })).toHaveCount(0);
  });

  test("a signed-out visitor is sent to login before the bag", async ({ page }) => {
    await page.goto("/cart");
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});
