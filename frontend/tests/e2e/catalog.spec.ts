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

    await expect(page.getByText("No matches for that search")).toBeVisible();
    await expect(plates(page)).toHaveCount(0);
  });

  /**
   * The two price boxes are independent inputs, so "min 30, max 20" is one careless entry
   * away — and the API answers that pair with a 422, which used to surface as a 500 page.
   */
  test("an inverted price range shows the empty state, not an error", async ({ page }) => {
    const response = await page.goto("/catalog?min_price=30&max_price=20");

    expect(response?.status()).toBe(200);
    await expect(page.getByText("Nothing matches all of those filters")).toBeVisible();
    await expect(plates(page)).toHaveCount(0);
    await expect(page.getByTestId("active-chip-min_price")).toBeVisible();
    await expect(page.getByTestId("active-chip-max_price")).toBeVisible();
  });

  test("an unusable price bound is dropped rather than sent to the API", async ({ page }) => {
    const response = await page.goto("/catalog?min_price=abc&max_price=-5");

    expect(response?.status()).toBe(200);
    expect(await plates(page).count()).toBeGreaterThan(0);
    await expect(page.getByTestId("active-chip-min_price")).toHaveCount(0);
    await expect(page.getByTestId("active-chip-max_price")).toHaveCount(0);
  });

  /**
   * The 2026-08-01 smoke test found all eight categories, both price fields and the stock
   * control sitting above the first product at 390x844. The disclosure is a real <details>,
   * so the assertions are about what the shopper can see, not about a class name.
   */
  test.describe("filters on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("the first product is reachable without scrolling past every filter", async ({
      page,
    }) => {
      await page.goto("/catalog");

      const disclosure = page.getByTestId("filters-disclosure");
      await expect(disclosure).toBeVisible();
      await expect(disclosure.getByLabel("Minimum price")).toBeHidden();

      const firstPlate = await plates(page).first().boundingBox();
      expect(firstPlate?.y ?? Infinity).toBeLessThan(844);
    });

    test("opening the disclosure reveals the filters", async ({ page }) => {
      await page.goto("/catalog");
      const disclosure = page.getByTestId("filters-disclosure");

      await disclosure.getByText("Filters").click();

      await expect(disclosure.getByLabel("Minimum price")).toBeVisible();
      await expect(disclosure.getByRole("button", { name: "Apply" })).toBeVisible();
    });

    test("an active filter is visible above the results while collapsed", async ({ page }) => {
      await page.goto("/catalog?category=ceramics&in_stock_only=true");

      await expect(page.getByTestId("active-filters")).toBeVisible();
      await expect(page.getByTestId("active-chip-category")).toBeVisible();
      await expect(page.getByTestId("active-chip-in_stock_only")).toBeVisible();
      await expect(
        page.getByTestId("filters-disclosure").getByLabel("Minimum price"),
      ).toBeHidden();
    });

    test("dropping a chip clears just that filter", async ({ page }) => {
      await page.goto("/catalog?category=ceramics&in_stock_only=true");

      await page.getByTestId("active-chip-in_stock_only").click();

      await expect(page).toHaveURL(/category=ceramics/);
      await expect(page).not.toHaveURL(/in_stock_only/);
      await expectPlatesShown(page);
    });
  });

  test("the filter rail is open by default on a desktop viewport", async ({ page }) => {
    await page.goto("/catalog");

    await expect(page.getByTestId("filters-disclosure")).toBeHidden();
    await expect(page.getByTestId("filters-rail").getByLabel("Minimum price")).toBeVisible();
  });

  test("a product page opens from the catalog", async ({ page }) => {
    await page.goto("/catalog");
    const name = (await plates(page).first().locator("a").nth(1).innerText()).trim();

    await plates(page).first().locator("a").nth(1).click();

    await expect(page).toHaveURL(/\/products\/\d+/);
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  });
});
