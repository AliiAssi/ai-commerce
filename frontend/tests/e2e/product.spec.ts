import { expect, test, type Page } from "@playwright/test";

/** Opens the first catalogue product's page and returns its name. */
async function openFirstProduct(page: Page): Promise<string> {
  await page.goto("/catalog");
  const link = page.locator('article.plate a[href^="/products/"]').nth(1);
  const name = (await link.innerText()).trim();
  // Navigated rather than clicked: a click here races the plate's reveal transition and has
  // landed on a stale href often enough to be worth removing from every test in this file.
  const href = await link.getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/products\/\d+/);
  return name;
}

test.describe("product page", () => {
  test("states its provenance and routes to the makers", async ({ page }) => {
    // an olive oil product, so the origin is one of the places we have written about
    await page.goto("/catalog?category=olive-oil");
    await page.locator("article.plate").first().getByRole("link").nth(1).click();
    await expect(page).toHaveURL(/\/products\/\d+/);

    const block = page.getByTestId("provenance");
    await expect(block).toBeVisible();

    await block.getByRole("link", { name: /Meet the makers/ }).click();
    await expect(page).toHaveURL(/\/makers/);
  });

  test("groups price and add into one buy box", async ({ page }) => {
    await openFirstProduct(page);

    const box = page.getByTestId("buy-box");
    await expect(box).toBeVisible();
    await expect(box.getByRole("button", { name: "Add to bag" })).toBeVisible();
    await expect(box.getByLabel("Quantity")).toBeVisible();
  });

  test("raises a buy bar on a phone once the box scrolls away", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    await openFirstProduct(page);

    const bar = page.getByTestId("buy-bar");

    // Driven off the box rather than off the fold: the square hero already pushes the box
    // under the fold on a phone, so asserting an initial state would only pin the viewport
    // arithmetic. What matters is that the bar tracks the box.
    await page.getByTestId("buy-box").scrollIntoViewIfNeeded();
    await expect(bar).toHaveAttribute("aria-hidden", "true");

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(bar).toHaveAttribute("aria-hidden", "false");
    await expect(bar.getByRole("button", { name: /Add to bag/ })).toBeVisible();
  });

  test("publishes structured data that matches what is on the page", async ({ page }) => {
    const name = await openFirstProduct(page);

    const raw = await page.locator('script[type="application/ld+json"]').innerText();
    const schema = JSON.parse(raw);

    expect(schema["@type"]).toBe("Product");
    expect(schema.name).toBe(name);
    expect(schema.offers.priceCurrency).toBe("USD");
    expect(schema.offers.availability).toContain("InStock");
  });

  test("never prints a reviewer's address", async ({ page }) => {
    await openFirstProduct(page);
    await expect(page.getByRole("heading", { name: /^Reviews/ })).toBeVisible();

    const main = await page.locator("main").innerText();
    expect(main).not.toMatch(/@[a-z0-9.-]+\.[a-z]{2,}/i);
  });

  /**
   * The related shelf streams in after the shell has hydrated, and RevealOnScroll marks each
   * plate the moment it lands. That mutation used to reach the DOM before React hydrated the
   * boundary, which surfaced as a hydration mismatch in the console.
   */
  test("streams the related shelf in without a hydration mismatch", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });

    await openFirstProduct(page);
    await expect(page.getByTestId("related-products")).toBeVisible();
    await page.waitForTimeout(1000);

    expect(errors.filter((e) => /hydrat|Minified React error/i.test(e))).toEqual([]);
  });

  test("offers somewhere to go next", async ({ page }) => {
    await openFirstProduct(page);

    const related = page.getByTestId("related-products");
    await expect(related).toBeVisible();
    await expect(related.locator("article.plate").first()).toBeVisible();
  });
});
