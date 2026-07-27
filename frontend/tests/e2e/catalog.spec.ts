import { expect, test, type Page } from "@playwright/test";

/**
 * Everything here navigates without changing the pathname, which is the family of bug that
 * kept reaching production: behaviour that only worked because Jinja did full page loads.
 * A plate that stays at `.reveal`'s opacity: 0 is invisible, so visibility is the assertion.
 */
const plates = (page: Page) => page.locator("article.plate");

/**
 * Playwright's toBeVisible() does NOT consider opacity — an element at opacity: 0 has a
 * bounding box and is not visibility:hidden, so it counts as visible. That is precisely the
 * failure mode here: a plate that never receives `.in` stays fully transparent while passing
 * every ordinary visibility check. So assert what the eye actually gets.
 */
async function expectPlatesShown(page: Page) {
  const first = plates(page).first();
  await expect(first).toBeVisible();
  await expect(first).toHaveClass(/\bin\b/);
  await expect
    .poll(async () => Number(await first.evaluate((el) => getComputedStyle(el).opacity)))
    .toBeGreaterThan(0.9);
}

test.describe("catalog", () => {
  test("sorting re-renders visible products", async ({ page }) => {
    await page.goto("/catalog");
    await expectPlatesShown(page);

    await page.getByLabel("Sort products").selectOption("price_asc");

    await expect(page).toHaveURL(/sort=price_asc/);
    await expectPlatesShown(page);
    await expect(plates(page)).toHaveCount(12);
  });

  test("sorting actually reorders", async ({ page }) => {
    await page.goto("/catalog?sort=price_asc");
    const cheapest = await page
      .locator("article.plate .font-serif.tabular-nums")
      .first()
      .innerText();

    await page.getByLabel("Sort products").selectOption("price_desc");
    await expect(page).toHaveURL(/sort=price_desc/);

    const dearest = await page
      .locator("article.plate .font-serif.tabular-nums")
      .first()
      .innerText();
    expect(Number(dearest.replace("$", ""))).toBeGreaterThan(Number(cheapest.replace("$", "")));
  });

  test("sorting keeps the URL free of empty filters", async ({ page }) => {
    await page.goto("/catalog");

    await page.getByLabel("Sort products").selectOption("rating");
    await expect(page).toHaveURL(/sort=rating/);

    expect(page.url()).toContain("sort=rating");
    expect(page.url()).not.toContain("q=");
    expect(page.url()).not.toContain("min_price=");
  });

  test("paginating re-renders visible products", async ({ page }) => {
    await page.goto("/catalog");

    await page.getByRole("link", { name: /Next/ }).click();

    await expect(page).toHaveURL(/page=2/);
    await expectPlatesShown(page);
  });

  test("sort survives pagination", async ({ page }) => {
    await page.goto("/catalog?sort=price_asc");

    await page.getByRole("link", { name: /Next/ }).click();

    await expect(page).toHaveURL(/sort=price_asc/);
    await expect(page).toHaveURL(/page=2/);
    await expectPlatesShown(page);
  });

  test("filtering by category re-renders visible products", async ({ page }) => {
    await page.goto("/catalog");

    // the footer repeats the shelf directory, so scope to the catalog rail
    await page
      .locator("aside")
      .getByRole("link", { name: /^Ceramics/ })
      .click();

    await expect(page).toHaveURL(/category=ceramics/);
    await expectPlatesShown(page);
  });

  test("a search with no matches shows the empty state", async ({ page }) => {
    await page.goto("/catalog?q=zzzznotathing");

    await expect(page.getByText("Nothing on this shelf")).toBeVisible();
    await expect(plates(page)).toHaveCount(0);
  });

  test("a product page opens from the catalog", async ({ page }) => {
    await page.goto("/catalog");
    const name = (await plates(page).first().locator("a").nth(1).innerText()).trim();

    await plates(page).first().locator("a").nth(1).click();

    await expect(page).toHaveURL(/\/products\/\d+/);
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  });
});
