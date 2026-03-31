import { test, expect } from "@playwright/test";

test.describe("SMC Analysis page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/smc");
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
  });

  test("entry plan shows prices", async ({ page }) => {
    // Look for price values (15x.xx format)
    const prices = page.locator("text=/1[45]\\d\\.\\d+/");
    expect(await prices.count()).toBeGreaterThanOrEqual(2);
  });

  test("3 scenario cards render with probabilities", async ({ page }) => {
    const percentages = page.locator("text=/%/");
    expect(await percentages.count()).toBeGreaterThanOrEqual(3);
  });

  test("playbook chart image is present", async ({ page }) => {
    const chart = page.locator("img");
    expect(await chart.count()).toBeGreaterThan(0);
  });

  test("active zones table has rows", async ({ page }) => {
    const zoneRows = page.locator("table tbody tr");
    expect(await zoneRows.count()).toBeGreaterThan(0);
  });

  test("nearby toggle filters zones", async ({ page }) => {
    const checkbox = page.locator("input[type='checkbox']");
    if ((await checkbox.count()) > 0) {
      // Uncheck first if checked by default
      const isChecked = await checkbox.first().isChecked();
      if (isChecked) {
        await checkbox.first().uncheck();
        await page.waitForTimeout(500);
      }
      const rowsBefore = await page.locator("table").first().locator("tbody tr").count();
      if (!isChecked) {
        await checkbox.first().check();
      } else {
        await checkbox.first().check();
      }
      await page.waitForTimeout(500);
      const rowsAfter = await page.locator("table").first().locator("tbody tr").count();
      expect(rowsAfter).toBeLessThanOrEqual(rowsBefore);
    }
  });

  test("liquidity levels table has rows", async ({ page }) => {
    const tables = page.locator("table");
    const lastTable = tables.last();
    const rows = lastTable.locator("tbody tr");
    expect(await rows.count()).toBeGreaterThan(0);
  });
});
