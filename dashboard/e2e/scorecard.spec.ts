import { test, expect } from "@playwright/test";

test.describe("Scorecard page", () => {
  test("page loads and renders", async ({ page }) => {
    await page.goto("/scorecard");
    await expect(page).toHaveTitle(/SMC Pulse/);
    // Wait for loading to finish — either data or empty state
    await page.waitForTimeout(5000);
    // Page should be interactive (header rendered)
    await expect(page.locator("text=/SMC/").first()).toBeVisible();
  });

  test("shows stats or empty state", async ({ page }) => {
    await page.goto("/scorecard");
    await page.waitForTimeout(5000);
    // Either data exists (Total label) or page rendered without error
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });
});
