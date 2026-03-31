import { test, expect } from "@playwright/test";

const switchToWeekly = async (page: import("@playwright/test").Page) => {
  await page.getByRole("button", { name: "Weekly", exact: true }).first().click();
  // Wait for the weekly-only "Policy & Politics" section to appear
  // This is Module 02 which only renders when weekly module_data is loaded
  await expect(
    page.locator("text=/Policy & Politics|政策與政治/").first()
  ).toBeVisible({ timeout: 30_000 });
};

test.describe("Reports page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/daily");
    await expect(page.locator(".animate-pulse").first()).toBeHidden({
      timeout: 15_000,
    });
  });

  test("tab switcher shows Daily and Weekly", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Daily", exact: true }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Weekly", exact: true }).first()
    ).toBeVisible();
  });

  test("date selector shows a date with navigation", async ({ page }) => {
    await expect(page.locator("text=/\\d{4}-\\d{2}-\\d{2}/")).toBeVisible();
    await expect(page.locator("button", { hasText: "←" })).toBeVisible();
    await expect(page.locator("button", { hasText: "→" })).toBeVisible();
  });

  test("Module 07 checklist renders signal grid", async ({ page }) => {
    await expect(
      page.locator("text=/LONG|SHORT|NEUTRAL|多頭|空頭|中性/").first()
    ).toBeVisible();
    await expect(
      page.locator("text=/Macro|Technicals|Cross-Asset/").first()
    ).toBeVisible();
  });

  test("Module 01 section shows spread data", async ({ page }) => {
    await expect(page.locator("text=/Spread|利差/").first()).toBeVisible();
  });

  test("Module 03 section shows technical indicators", async ({ page }) => {
    await expect(page.locator("text=/RSI/").first()).toBeVisible();
  });

  test("Module 05 section shows correlation table", async ({ page }) => {
    await expect(
      page.locator("text=/S&P 500|Nikkei|Gold|VIX/").first()
    ).toBeVisible();
  });

  test("switch to Weekly tab shows Modules 02, 04, 06", async ({ page }) => {
    await switchToWeekly(page);
    // Module 04: Positioning section header
    await expect(
      page.locator("text=/Positioning|持倉分析/").first()
    ).toBeVisible();
    // Module 06: Seasonality section header
    await expect(
      page.locator("text=/Seasonality|季節性/").first()
    ).toBeVisible();
  });

  test("Module 02 shows BOJ and Fed cards", async ({ page }) => {
    await switchToWeekly(page);
    // BOJ card within the Policy section (not checklist row)
    const policySection = page.locator("text=/Policy & Politics|政策與政治/").first().locator("../..");
    await expect(page.locator(".bg-bg-secondary >> text=BOJ").first()).toBeVisible();
    await expect(page.locator(".bg-bg-secondary >> text=Fed").first()).toBeVisible();
  });

  test("Module 04 shows net position", async ({ page }) => {
    await switchToWeekly(page);
    // Look for the contracts text or the large number
    await expect(
      page.locator("text=/contracts|合約/").first()
    ).toBeVisible();
  });

  test("Module 06 shows upcoming events table", async ({ page }) => {
    await switchToWeekly(page);
    await expect(
      page.locator("text=/Event|事件|Impact|影響/").first()
    ).toBeVisible();
  });

  test("date navigation changes the report", async ({ page }) => {
    const dateText = page.locator("text=/\\d{4}-\\d{2}-\\d{2}/");
    const currentDate = await dateText.textContent();
    const prevBtn = page.locator("button", { hasText: "←" });
    if (await prevBtn.isEnabled()) {
      await prevBtn.click();
      await page.waitForTimeout(1500);
      const newDate = await dateText.textContent();
      expect(newDate).not.toBe(currentDate);
    }
  });
});
