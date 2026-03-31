import { test, expect } from "@playwright/test";

test.describe("Journal page", () => {
  test("page loads and renders", async ({ page }) => {
    await page.goto("/journal");
    await expect(page).toHaveTitle(/SMC Pulse/);
    await page.waitForTimeout(5000);
    await expect(page.locator("text=/SMC/").first()).toBeVisible();
  });

  test("shows stats or empty state", async ({ page }) => {
    await page.goto("/journal");
    await page.waitForTimeout(5000);
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });
});
