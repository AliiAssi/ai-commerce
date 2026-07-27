import { expect, type Locator, type Page } from "@playwright/test";

export const PASSWORD = "Password#123";

/** A fresh account per test, so tests never contend over one user's cart or orders. */
export function newEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.test`;
}

/**
 * The desktop account dropdown. The header renders the signed-in email twice — once here and
 * once in the mobile panel, which is present in the DOM but CSS-hidden — so assertions have
 * to say which one they mean.
 */
export function accountMenu(page: Page): Locator {
  return page
    .locator("details.menu")
    .filter({ has: page.locator("summary", { hasText: "@" }) });
}

export function cartBadge(page: Page): Locator {
  return page.getByRole("link", { name: /^Cart/ }).first();
}

export async function register(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).not.toHaveURL(/\/register/);
  await expect(accountMenu(page)).toBeVisible();
}

export async function login(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

export async function logout(page: Page): Promise<void> {
  const menu = accountMenu(page);
  await menu.locator("summary").click();
  await menu.getByRole("button", { name: "Log out" }).click();
  await expect(accountMenu(page)).toHaveCount(0);
}

/** Adds the first in-stock product on the catalog to the bag, returning its name. */
export async function addFirstProductToBag(page: Page): Promise<string> {
  await page.goto("/catalog");
  const plate = page.locator("article.plate").first();
  const name = (await plate.getByRole("link").nth(1).innerText()).trim();
  await plate.hover();
  await plate.getByRole("button", { name: /Add .* to bag/ }).click();
  // the badge moves optimistically, before the server has confirmed; the toast is only
  // shown once the action resolved, so that is what tells us the cart really changed
  await expect(page.getByText("Added to your bag")).toBeVisible();
  return name;
}
