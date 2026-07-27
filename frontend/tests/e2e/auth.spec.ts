import { expect, test } from "@playwright/test";

import { accountMenu, login, logout, newEmail, PASSWORD, register } from "./support";

test.describe("auth", () => {
  test("registering signs you in and the header updates without a reload", async ({ page }) => {
    const email = newEmail("reg");
    await register(page, email);

    // the defect this guards: the header cached a signed-out session and only corrected on
    // a full refresh, because the App Router keeps the layout mounted across navigation
    await expect(accountMenu(page)).toContainText(email);
  });

  test("logging in updates the header without a reload", async ({ page }) => {
    const email = newEmail("login");
    await register(page, email);
    await logout(page);

    await login(page, email);

    await expect(accountMenu(page)).toContainText(email);
  });

  test("logging out updates the header without a reload", async ({ page }) => {
    await register(page, newEmail("out"));

    await logout(page);

    await expect(accountMenu(page)).toHaveCount(0);
  });

  test("the account menu closes when an item inside it is chosen", async ({ page }) => {
    const email = newEmail("menu");
    await register(page, email);
    await page.goto("/");

    const menu = accountMenu(page);
    await menu.locator("summary").click();
    await expect(menu).toHaveAttribute("open", "");

    await menu.getByRole("link", { name: "My orders" }).click();

    await expect(page).toHaveURL(/\/account\/orders/);
    // it used to hang open over the page it had just navigated to
    await expect(page.locator("details.menu[open]")).toHaveCount(0);

    // Choosing the page you are already on is the case that isolates the click handler:
    // the pathname does not change, so the navigation fallback cannot mask a regression.
    await menu.locator("summary").click();
    await expect(menu).toHaveAttribute("open", "");
    await menu.getByRole("link", { name: "My orders" }).click();
    await expect(page.locator("details.menu[open]")).toHaveCount(0);
  });

  test("the header is right on reload before /api/session answers", async ({ page }) => {
    const email = newEmail("reload");
    await register(page, email);
    await page.goto("/");

    // Hold the session probe open. Locally it answers in ~50ms, which is fast enough to hide
    // a missing cache behind any plausible timeout — so the only honest way to assert "the
    // header did not wait on the network" is to make the network unmistakably slow.
    await page.route("**/api/session", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4_000));
      await route.continue();
    });

    await page.reload();

    await expect(accountMenu(page)).toContainText(email, { timeout: 1_500 });
  });

  test("the footer account column follows the session too", async ({ page }) => {
    const email = newEmail("footer");
    await register(page, email);
    await page.goto("/about");

    const column = page.getByRole("navigation", { name: "Account" });
    await expect(column.getByRole("link", { name: "My orders" })).toBeVisible();
    await expect(column.getByRole("link", { name: "Log in" })).toHaveCount(0);
  });

  test("a wrong password reports an error and does not sign you in", async ({ page }) => {
    const email = newEmail("bad");
    await register(page, email);
    await logout(page);

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Log in" }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("protected routes bounce to login carrying a next target", async ({ page }) => {
    await page.goto("/account/orders");
    await expect(page).toHaveURL(/\/login\?next=/);
  });

  test("an off-site next target is refused", async ({ page }) => {
    const email = newEmail("evil");
    await register(page, email);
    await logout(page);

    await page.goto("/login?next=https://evil.test/steal");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();

    await expect(accountMenu(page)).toBeVisible();
    expect(page.url()).toContain("127.0.0.1");
  });
});
