import { expect, test, type Page } from "@playwright/test";

import { addFirstProductToBag, newEmail, register } from "./support";

async function firstProductHref(page: Page): Promise<string> {
  await page.goto("/catalog");
  const link = page.locator('article.plate a[href^="/products/"]').nth(1);
  return (await link.getAttribute("href"))!;
}

/** Buys the first catalogue product outright, which is what makes the buyer eligible. */
async function buyFirstProduct(page: Page): Promise<string> {
  const name = await addFirstProductToBag(page);
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Place order" }).click();
  await expect(page).toHaveURL(/\/checkout\/done\//);
  return name;
}

test.describe("who is offered the review composer", () => {
  test("a signed-out visitor is told where reviews come from, not given a form", async ({
    page,
  }) => {
    await page.goto(await firstProductHref(page));

    await expect(page.getByTestId("review-gate")).toBeVisible();
    await expect(page.getByTestId("review-composer")).toHaveCount(0);
  });

  /**
   * The whole point of the eligibility endpoint: before it existed this shopper got a full
   * form and learned it would be refused only after writing the review.
   */
  test("a signed-in non-purchaser gets no form either", async ({ page }) => {
    await register(page, newEmail("nonbuyer"));
    await page.goto(await firstProductHref(page));

    await expect(page.getByTestId("review-gate")).toBeVisible();
    await expect(page.getByTestId("review-composer")).toHaveCount(0);
  });

  test("a purchaser writes one from the stars and then sees it as theirs", async ({ page }) => {
    await register(page, newEmail("buyer"));
    await buyFirstProduct(page);
    await page.goto(await firstProductHref(page));

    const composer = page.getByTestId("review-composer");
    await expect(composer).toBeVisible();

    // nothing to fill in until a star is chosen
    await expect(composer.getByRole("textbox")).toHaveCount(0);
    await composer.getByRole("radio", { name: /4 stars/ }).click();

    const text = composer.getByRole("textbox");
    await expect(text).toBeVisible();
    await text.fill("Arrived quickly and the quality is obvious.");
    await composer.getByRole("button", { name: "Post review" }).click();

    const mine = page.getByTestId("your-review");
    await expect(mine).toBeVisible();
    await expect(mine).toContainText("Arrived quickly");

    // and it is still theirs after a reload, from the server rather than local state
    await page.reload();
    await expect(page.getByTestId("your-review")).toBeVisible();
    await expect(page.getByTestId("review-composer")).toHaveCount(0);
  });

  test("the same composer is offered on the order it came from", async ({ page }) => {
    await register(page, newEmail("orderreview"));
    const name = await buyFirstProduct(page);

    await page.goto("/account/orders");
    await page
      .getByRole("link", { name: /^Order #/ })
      .first()
      .click();
    await expect(page).toHaveURL(/\/account\/orders\/\d+/);

    const composer = page.getByTestId("review-composer");
    await expect(composer).toBeVisible();
    await expect(composer).toContainText(`Rate ${name}`);

    await composer.getByRole("radio", { name: /5 stars/ }).click();
    await composer.getByRole("textbox").fill("Exactly what I hoped for.");
    await composer.getByRole("button", { name: "Post review" }).click();

    await expect(page.getByTestId("your-review")).toBeVisible();
  });

  test("the review is refused a second time, on both surfaces", async ({ page }) => {
    await register(page, newEmail("once"));
    await buyFirstProduct(page);
    const href = await firstProductHref(page);

    await page.goto(href);
    const composer = page.getByTestId("review-composer");
    await composer.getByRole("radio", { name: /3 stars/ }).click();
    await composer.getByRole("textbox").fill("Fine, does the job.");
    await composer.getByRole("button", { name: "Post review" }).click();
    await expect(page.getByTestId("your-review")).toBeVisible();

    await page.goto("/account/orders");
    await page
      .getByRole("link", { name: /^Order #/ })
      .first()
      .click();
    await expect(page.getByTestId("your-review")).toBeVisible();
    await expect(page.getByTestId("review-composer")).toHaveCount(0);
  });
});
