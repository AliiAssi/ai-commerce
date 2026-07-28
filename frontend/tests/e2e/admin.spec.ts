import { expect, test, type Page } from "@playwright/test";

import { loginAs, newEmail, register } from "./support";

const ADMIN = { email: "admin@beit.test", password: "Password#123" };

/** Creates a product through the admin form so a test can mutate it without disturbing others. */
async function createProduct(page: Page): Promise<string> {
  const name = `E2E Product ${Date.now()}-${Math.floor(Math.random() * 1e4)}`;
  await page.goto("/admin/products/new");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Price ($)").fill("19.00");
  await page.getByLabel("Initial stock").fill("9");
  await page.getByLabel("Description").fill("Created by the end-to-end suite.");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page).toHaveURL(/\/admin\/products$/);
  return name;
}

test.describe("admin", () => {
  test("a customer cannot reach the admin area", async ({ page }) => {
    await register(page, newEmail("nonadmin"));
    await page.goto("/admin");
    await expect(page.getByText("This area is restricted")).toBeVisible();
  });

  test("a signed-out visitor is sent to login", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login\?next=/);
  });

  test("the dashboard shows the store's numbers", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin");

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Revenue")).toBeVisible();
    await expect(page.getByText("Low stock")).toBeVisible();
    await expect(page.getByText("Recent activity")).toBeVisible();
  });

  test("adjusting stock updates the row in place", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin/products");

    const row = page.locator("tbody tr").first();
    const before = Number(await row.locator("td").nth(2).locator("span").first().innerText());

    await row.getByRole("button", { name: /^Increase stock/ }).click();
    await expect(row.locator("td").nth(2).locator("span").first()).toHaveText(
      String(before + 1),
    );

    await row.getByRole("button", { name: /^Decrease stock/ }).click();
    await expect(row.locator("td").nth(2).locator("span").first()).toHaveText(String(before));
  });

  /** The row keeps its own state; a reload must not show a number the server disagrees with. */
  test("a stock change survives a reload", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin/products");

    const row = page.locator("tbody tr").first();
    const cell = row.locator("td").nth(2).locator("span").first();
    const before = Number(await cell.innerText());

    await row.getByRole("button", { name: /^Increase stock/ }).click();
    await expect(cell).toHaveText(String(before + 1));

    await page.reload();
    await expect(
      page.locator("tbody tr").first().locator("td").nth(2).locator("span").first(),
    ).toHaveText(String(before + 1));

    // put it back so the suite can be re-run against the same database
    await page
      .locator("tbody tr")
      .first()
      .getByRole("button", { name: /^Decrease stock/ })
      .click();
  });

  test("archiving moves a product between tabs, and it stays editable", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    const name = await createProduct(page);

    await page.goto(`/admin/products?q=${encodeURIComponent(name)}`);
    const row = page.locator("tbody tr").first();
    await row.getByRole("button", { name: "Archive" }).click();
    await expect(row.getByRole("button", { name: "Unarchive" })).toBeVisible();

    await page.goto(`/admin/products?q=${encodeURIComponent(name)}&status=archived`);
    await expect(page.getByRole("link", { name })).toBeVisible();

    await page.goto(`/admin/products?q=${encodeURIComponent(name)}&status=active`);
    await expect(page.getByText("No products match")).toBeVisible();

    // G6: the public product endpoint 404s an archived product; the admin one must not
    await page.goto(`/admin/products?q=${encodeURIComponent(name)}&status=archived`);
    await page.getByRole("link", { name }).click();
    await expect(page).toHaveURL(/\/admin\/products\/\d+\/edit/);
    await expect(page.getByRole("heading", { name: `Edit: ${name}` })).toBeVisible();

    await page.goto(`/admin/products?q=${encodeURIComponent(name)}&status=archived`);
    await page.locator("tbody tr").first().getByRole("button", { name: "Unarchive" }).click();
    await expect(
      page.locator("tbody tr").first().getByRole("button", { name: "Archive" }),
    ).toBeVisible();
  });

  test("creating a product adds it to the catalog and the audit log", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin/products/new");

    const name = `E2E Kettle ${Date.now()}`;
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Price ($)").fill("42.00");
    await page.getByLabel("Initial stock").fill("7");
    await page.getByLabel("Description").fill("A kettle created by the end-to-end suite.");
    await page.getByRole("button", { name: "Save product" }).click();

    await expect(page).toHaveURL(/\/admin\/products$/);
    await page.goto(`/admin/products?q=${encodeURIComponent(name)}`);
    await expect(page.getByRole("link", { name })).toBeVisible();

    await page.goto("/admin/audit");
    await expect(page.getByText("product_create").first()).toBeVisible();
  });

  test("advancing an order moves it through its lifecycle", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin/orders?status=paid");

    const row = page.locator("tbody tr").first();
    await expect(row.getByRole("button", { name: "Mark shipped" })).toBeVisible();
    await row.getByRole("button", { name: "Mark shipped" }).click();

    // the row re-renders from the action's response, without a page reload
    await expect(row.getByRole("button", { name: "Mark delivered" })).toBeVisible();
    await expect(row.getByText("Shipped")).toBeVisible();
  });

  test("the status tabs count and filter consistently", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin/orders");

    for (const status of ["Paid", "Shipped", "Delivered"]) {
      const tab = page.getByRole("link", { name: new RegExp(`^${status}`) });
      const count = Number((await tab.innerText()).replace(/\D/g, ""));
      await tab.click();
      await expect(page).toHaveURL(new RegExp(`status=${status.toLowerCase()}`));
      await expect(page.locator("tbody tr")).toHaveCount(count);
    }
  });

  test("the sidebar marks the current section", async ({ page }) => {
    await loginAs(page, ADMIN.email, ADMIN.password);
    await page.goto("/admin");

    const sidebar = page.locator("aside");
    await expect(sidebar.getByRole("link", { name: "Dashboard" })).toHaveClass(
      /bg-sidebar-active/,
    );

    await sidebar.getByRole("link", { name: "Products" }).click();
    await expect(page).toHaveURL(/\/admin\/products/);
    // /admin must not stay lit once a deeper section is open
    await expect(sidebar.getByRole("link", { name: "Dashboard" })).not.toHaveClass(
      /bg-sidebar-active/,
    );
    await expect(sidebar.getByRole("link", { name: "Products" })).toHaveClass(
      /bg-sidebar-active/,
    );
  });
});
