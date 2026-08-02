import { expect, test } from "@playwright/test";

import { addFirstProductToBag, newEmail, register } from "./support";

/**
 * Areas the earlier specs left uncovered, plus the cases most likely to hold the same defect
 * as the four already found: state that used to be rebuilt by a full page load and now has to
 * survive client-side navigation.
 */

test.describe("header search", () => {
  test("shows the query you are actually looking at", async ({ page }) => {
    await page.goto("/");

    await page.getByTestId("header-search").first().fill("soap");
    await page.getByTestId("header-search").first().press("Enter");

    await expect(page).toHaveURL(/q=soap/);
    // the input is in the persistent layout, so nothing remounts it on navigation
    await expect(page.getByTestId("header-search").first()).toHaveValue("soap");
  });

  test("updates when the query changes again", async ({ page }) => {
    await page.goto("/catalog?q=soap");
    await expect(page.getByTestId("header-search").first()).toHaveValue("soap");

    await page.goto("/catalog?q=oil");
    await expect(page.getByTestId("header-search").first()).toHaveValue("oil");
  });

  test("clears when a client-side navigation drops the query", async ({ page }) => {
    await page.goto("/catalog?q=soap");
    await expect(page.getByTestId("header-search").first()).toHaveValue("soap");

    // the footer's Everything goes to a bare /catalog; the header never remounts on a
    // client-side navigation, so the box has to notice the query went away
    await page
      .getByRole("navigation", { name: "The shelves" })
      .getByRole("link", { name: "Everything" })
      .click();

    await expect(page).toHaveURL(/\/catalog$/);
    await expect(page.getByTestId("header-search").first()).toHaveValue("");
  });

  test("discards typing you abandoned when the URL moves on", async ({ page }) => {
    await page.goto("/catalog?q=soap");

    // typing makes the input dirty, so the browser stops reflecting the value attribute —
    // without a remount the abandoned term would sit there contradicting the results
    const box = page.getByTestId("header-search").first();
    await box.fill("something else entirely");

    await page
      .getByRole("navigation", { name: "The shelves" })
      .getByRole("link", { name: "Everything" })
      .click();

    await expect(page).toHaveURL(/\/catalog$/);
    await expect(page.getByTestId("header-search").first()).toHaveValue("");
  });

  /**
   * Everything is a category link like any other, so it ends the search too — §5.3. The
   * regression it still guards is the category half: it must actually clear `category`, not
   * merely swap it, and the search box must agree with the URL rather than showing a term the
   * results no longer reflect.
   */
  test("the rail's Everything clears both the category and the search", async ({ page }) => {
    await page.goto("/catalog?q=soap&category=soap-skincare");

    await page.getByRole("link", { name: /^Everything \d/ }).click();

    await expect(page).not.toHaveURL(/category=/);
    await expect(page).not.toHaveURL(/[?&]q=/);
    await expect(page.getByTestId("header-search").first()).toHaveValue("");
  });

  test("a category link keeps explicit filters while dropping the term", async ({ page }) => {
    await page.goto("/catalog?q=soap&category=soap-skincare&in_stock_only=true");

    await page.getByRole("link", { name: /^Everything \d/ }).click();

    await expect(page).toHaveURL(/in_stock_only=true/);
    await expect(page).not.toHaveURL(/[?&]q=/);
  });
});

test.describe("assistant widget", () => {
  test("the launcher opens the panel", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Open the store assistant" }).click();
    await expect(page.getByRole("dialog", { name: "Store assistant" })).toBeVisible();
  });

  test("Escape closes it", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Open the store assistant" }).click();
    await expect(page.getByRole("dialog", { name: "Store assistant" })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Store assistant" })).not.toBeVisible();
  });

  test("the hero trigger works after navigating to the home page", async ({ page }) => {
    // Arriving on / directly is the easy case. The widget mounts once in the layout, so the
    // interesting case is reaching the home page by client-side navigation, after the hero
    // button did not exist at mount time.
    await page.goto("/catalog");
    await page.getByRole("link", { name: "BEIT" }).first().click();
    await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/$/);

    await page.getByRole("button", { name: /Ask the assistant/ }).click();

    await expect(page.getByRole("dialog", { name: "Store assistant" })).toBeVisible();
  });
});

test.describe("theme", () => {
  test("the toggle switches and survives a reload", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");

    await page.getByRole("button", { name: /Switch to (dark|light) theme/ }).click();
    const chosen = await html.getAttribute("data-theme");
    expect(chosen).toBeTruthy();

    await page.reload();
    // the pre-paint script in app/layout.tsx must apply it before anything renders
    await expect(html).toHaveAttribute("data-theme", chosen!);
  });
});

test.describe("reviews", () => {
  test("a signed-out visitor is invited to log in", async ({ page }) => {
    await page.goto("/products/1");
    await expect(page.getByRole("link", { name: "Log in" }).last()).toBeVisible();
  });

  test("a signed-in customer can leave one and see it appear", async ({ page }) => {
    await register(page, newEmail("review"));
    await page.goto("/products/1");

    const text = `Genuinely good, tested end to end ${Date.now()}`;
    await page.getByLabel("Your review").fill(text);
    await page.getByRole("button", { name: "Submit review" }).click();

    await expect(page.getByText(text)).toBeVisible();
  });
});

test.describe("adding to the bag", () => {
  /**
   * The client cannot read the httpOnly session cookie, so immediately after a page load it
   * genuinely does not know who you are. Treating "not loaded yet" as "signed out" bounced
   * signed-in shoppers to the login page if they clicked before /api/session answered.
   */
  test("works when clicked before the session probe answers", async ({ page }) => {
    await register(page, newEmail("race"));

    await page.route("**/api/session", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 5_000));
      await route.continue();
    });
    await page.goto("/catalog");

    const plate = page.locator("article.plate").first();
    const add = plate.getByRole("button", { name: /Add .* to bag/ });
    await plate.hover();
    await add.click();

    await expect(add).toHaveAttribute("data-added", "true");
    await expect(page).not.toHaveURL(/\/login/);
  });

  test("sends a genuinely signed-out visitor to log in", async ({ page }) => {
    await page.goto("/catalog");

    const plate = page.locator("article.plate").first();
    await plate.hover();
    await plate.getByRole("button", { name: /Add .* to bag/ }).click();

    await expect(page).toHaveURL(/\/login\?next=/);
  });
});

test.describe("cart badge across navigation", () => {
  test("stays correct when moving between pages", async ({ page }) => {
    await register(page, newEmail("badge"));
    await addFirstProductToBag(page);

    await page.goto("/about");
    await expect(page.getByRole("link", { name: /^Cart \(/ }).first()).toHaveAccessibleName(
      /1 item/,
    );

    await page.goto("/catalog");
    await expect(page.getByRole("link", { name: /^Cart \(/ }).first()).toHaveAccessibleName(
      /1 item/,
    );
  });
});
