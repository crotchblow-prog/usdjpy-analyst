import { test, expect } from "@playwright/test";

test.describe("Dashboard home", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("data loads and hero card shows direction", async ({ page }) => {
    // Wait for skeleton to disappear
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
    // Direction symbol should be visible (▲ or ▼ or ◆)
    await expect(page.locator("text=/[▲▼◆]/").first()).toBeVisible();
  });

  test("hero card shows entry plan metrics", async ({ page }) => {
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
    // Entry, Stop, T1, T2 labels
    for (const label of ["Entry", "Stop", "T1", "T2"]) {
      await expect(page.locator(`text=${label}`).first()).toBeVisible();
    }
  });

  test("market structure card shows 4 timeframes", async ({ page }) => {
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
    for (const tf of ["4H", "1H", "15M", "5M"]) {
      await expect(page.locator(`text=${tf}`).first()).toBeVisible();
    }
  });

  test("liquidity levels table has rows", async ({ page }) => {
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
    const table = page.locator("table").last();
    const rows = table.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
  });

  test("stale indicator shows last updated", async ({ page }) => {
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
    await expect(page.locator("text=/Last updated|最後更新/")).toBeVisible();
  });
});
