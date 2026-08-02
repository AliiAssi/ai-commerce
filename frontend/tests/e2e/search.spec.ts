import { expect, test, type Page } from "@playwright/test";

/**
 * Smart search, driven through the whole chain: browser → Next → web → ai → database.
 *
 * The stack script and CI both run the AI service with routing enabled, because retrieval
 * lives there — without it this suite would only ever exercise web's lexical fallback and
 * every assertion about chips below would silently pass by never rendering anything.
 *
 * These are §17's Frontend/E2E requirements: plain-GET forms, Arabic input direction, chips
 * that survive sort and pagination, conditional relevance, and no state dropped from links.
 */
const plates = (page: Page) => page.locator("article.plate");
const chips = (page: Page) => page.getByTestId("inferred-chips");

async function search(page: Page, query: string) {
  await page.goto(`/catalog?q=${encodeURIComponent(query)}`);
}

test.describe("search entry", () => {
  test("the header search is a plain GET form", async ({ page }) => {
    await page.goto("/");
    const form = page.locator('form[action="/catalog"]').first();

    await expect(form).toHaveAttribute("method", /get/i);
  });

  test("searching from the header lands on the catalog with the query in the URL", async ({
    page,
  }) => {
    await page.goto("/");
    const input = page.locator('form[action="/catalog"] input[name="q"]').first();
    await input.fill("olive oil");
    await input.press("Enter");

    await expect(page).toHaveURL(/\/catalog\?q=olive\+oil|\/catalog\?q=olive%20oil/);
    await expect(plates(page).first()).toBeVisible();
  });

  test("the search input renders either language in its own direction", async ({ page }) => {
    // §5.1: a fixed dir would render one of the two languages backwards.
    await page.goto("/catalog");
    const input = page.locator('aside input[name="q"]');

    await expect(input).toHaveAttribute("dir", "auto");
  });

  test("the shopper's original query stays in the box", async ({ page }) => {
    await search(page, "زيت زيتون");

    await expect(page.locator('aside input[name="q"]')).toHaveValue("زيت زيتون");
  });
});

test.describe("interpreted filters", () => {
  test("what the parser understood is shown as chips", async ({ page }) => {
    await search(page, "soap from Tripoli");

    await expect(chips(page)).toBeVisible();
    await expect(page.getByTestId("chip-origin")).toContainText("Tripoli");
  });

  test("a price phrase becomes a chip and narrows the results", async ({ page }) => {
    await search(page, "olive oil under $25");

    await expect(page.getByTestId("chip-max_price")).toContainText("Under $25");
  });

  test("removing a chip keeps the visible query unchanged", async ({ page }) => {
    // §5.2.1: the URL must never contradict the search box.
    await search(page, "housewarming gift from Bcharre under $30");
    await page.getByTestId("chip-origin").click();

    await expect(page).toHaveURL(/ignore_inferred=origin/);
    await expect(page.locator('aside input[name="q"]')).toHaveValue(
      "housewarming gift from Bcharre under $30",
    );
  });

  test("removing a chip widens the results but keeps the others", async ({ page }) => {
    await search(page, "housewarming gift from Bcharre under $30");
    const narrow = await plates(page).count();

    await page.getByTestId("chip-max_price").click();

    await expect(page.getByTestId("chip-max_price")).toHaveCount(0);
    await expect(page.getByTestId("chip-origin")).toBeVisible();
    expect(await plates(page).count()).toBeGreaterThan(narrow);
  });

  test("a suppressed inference survives a sort change", async ({ page }) => {
    await search(page, "housewarming gift from Bcharre under $30");
    await page.getByTestId("chip-origin").click();
    await expect(page).toHaveURL(/ignore_inferred=origin/);

    await page.getByLabel("Sort products").selectOption("price_asc");

    await expect(page).toHaveURL(/ignore_inferred=origin/);
    await expect(page).toHaveURL(/sort=price_asc/);
    await expect(page).toHaveURL(/q=/);
  });

  /**
   * Picking a category is a browse gesture, so it ends the search rather than intersecting
   * with it. `ignore_inferred` goes with it: those names refer to inferences drawn from `q`,
   * so keeping them without `q` would leave suppressions with nothing left to suppress.
   */
  test("a category link clears the search term", async ({ page }) => {
    await search(page, "gift from Bcharre under $30");
    await page.getByTestId("chip-origin").click();
    // Wait for the chip's navigation to land, or the category link clicked below is still the
    // one the previous render drew — which carries no ignore_inferred and passes vacuously.
    await expect(page).toHaveURL(/ignore_inferred=origin/);

    await page
      .locator("aside")
      .getByRole("link", { name: /^Cedar/ })
      .click();

    await expect(page).toHaveURL(/category=woodwork/);
    await expect(page).not.toHaveURL(/[?&]q=/);
    await expect(page).not.toHaveURL(/ignore_inferred/);
    await expect(page).not.toHaveURL(/sort=relevance/);
  });

  test("explicit filters survive a category link even though the term does not", async ({
    page,
  }) => {
    await page.goto("/catalog?q=soap&max_price=30&in_stock_only=true");

    await page
      .locator("aside")
      .getByRole("link", { name: /^Cedar/ })
      .click();

    await expect(page).toHaveURL(/category=woodwork/);
    await expect(page).toHaveURL(/max_price=30/);
    await expect(page).toHaveURL(/in_stock_only=true/);
    await expect(page).not.toHaveURL(/[?&]q=/);
  });

  test("the search term has its own chip that clears only the term", async ({ page }) => {
    await page.goto("/catalog?q=soap&max_price=30");

    await expect(page.getByTestId("active-chip-q")).toBeVisible();
    await page.getByTestId("active-chip-q").click();

    await expect(page).not.toHaveURL(/[?&]q=/);
    await expect(page).toHaveURL(/max_price=30/);
  });
});

test.describe("relevance sorting", () => {
  test("relevance is offered only when a query is active", async ({ page }) => {
    await page.goto("/catalog");
    await expect(page.getByLabel("Sort products").locator("option")).not.toContainText([
      "Relevance",
    ]);

    await search(page, "olive oil");
    await expect(
      page.getByLabel("Sort products").locator('option[value="relevance"]'),
    ).toHaveCount(1);
  });

  test("relevance is the default with a query, and stays out of the URL", async ({ page }) => {
    await search(page, "olive oil");

    await expect(page.getByLabel("Sort products")).toHaveValue("relevance");
    expect(page.url()).not.toContain("sort=");
  });

  test("browsing defaults to newest", async ({ page }) => {
    await page.goto("/catalog");

    await expect(page.getByLabel("Sort products")).toHaveValue("newest");
  });

  test("an explicit sort reorders the matched set rather than the whole catalog", async ({
    page,
  }) => {
    await search(page, "olive oil");
    const matched = await plates(page).count();

    await page.getByLabel("Sort products").selectOption("price_asc");

    await expect(page).toHaveURL(/sort=price_asc/);
    await expect(page).toHaveURL(/q=/);
    expect(await plates(page).count()).toBe(matched);
  });
});

test.describe("preserved state", () => {
  test("a query survives pagination", async ({ page }) => {
    await search(page, "lebanese");
    await expect(page.getByRole("link", { name: /Next/ })).toBeVisible();

    await page.getByRole("link", { name: /Next/ }).click();

    await expect(page).toHaveURL(/page=2/);
    await expect(page).toHaveURL(/q=lebanese/);
    await expect(plates(page).first()).toBeVisible();
  });

  test("an explicit price filter survives a search", async ({ page }) => {
    await page.goto("/catalog?q=olive&max_price=20");

    await expect(page.locator('aside input[name="max_price"]')).toHaveValue("20");
    await expect(page).toHaveURL(/q=olive/);
  });

  test("the sidebar form keeps the query when a price is applied", async ({ page }) => {
    await search(page, "olive oil");
    await page.locator('aside input[name="max_price"]').fill("20");
    await page.getByRole("button", { name: "Apply" }).click();

    await expect(page).toHaveURL(/max_price=20/);
    await expect(page).toHaveURL(/q=olive/);
  });
});

test.describe("bilingual behaviour", () => {
  test("an Arabic query resolves its filters and returns products", async ({ page }) => {
    // No Arabic text exists in the catalog, so the deterministic filters are the whole answer
    // until the embedding phases land — which is exactly what this proves still works.
    await search(page, "صابون من طرابلس");

    await expect(plates(page).first()).toBeVisible();
    await expect(page.getByTestId("chip-origin")).toBeVisible();
  });

  test("Arabic search feedback renders right-to-left", async ({ page }) => {
    await search(page, "صابون من طرابلس");

    await expect(chips(page)).toHaveAttribute("dir", "rtl");
  });

  test("an Arabic no-result search explains itself in Arabic", async ({ page }) => {
    await search(page, "زززلاشيء");

    await expect(page.getByText("لا نتائج لهذا البحث")).toBeVisible();
  });
});

test.describe("empty states", () => {
  test("no matches reads differently from filters being too narrow", async ({ page }) => {
    await search(page, "zzzznotathing");
    await expect(page.getByText("No matches for that search")).toBeVisible();

    await page.goto("/catalog?q=olive+oil&max_price=1");
    await expect(page.getByText("Nothing matches all of those filters")).toBeVisible();
  });

  test("an empty state offers a way back to browsing", async ({ page }) => {
    await search(page, "zzzznotathing");

    await page.getByRole("link", { name: "Browse everything" }).click();

    await expect(page).toHaveURL(/\/catalog$/);
    await expect(plates(page).first()).toBeVisible();
  });
});

test.describe("honesty", () => {
  test("no provider or internal detail is ever rendered", async ({ page }) => {
    // §12: customer-facing copy must not expose "Ollama", "pgvector", keys or exceptions.
    await search(page, "olive oil under $25");
    const body = ((await page.locator("body").textContent()) ?? "").toLowerCase();

    for (const leak of ["ollama", "pgvector", "traceback", "internal-key", "asyncpg"]) {
      expect(body).not.toContain(leak);
    }
  });

  test("no relevance score is shown on a product", async ({ page }) => {
    // §7.4 keeps scores off the public contract, and §4 rules out a score badge.
    await search(page, "olive oil");
    const body = ((await page.locator("body").textContent()) ?? "").toLowerCase();

    expect(body).not.toContain("rrf");
    expect(body).not.toContain("similarity");
  });
});
