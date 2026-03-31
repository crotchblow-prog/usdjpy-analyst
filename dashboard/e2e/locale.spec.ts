import { test, expect } from "@playwright/test";

test.describe("Locale toggle", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("defaults to English", async ({ page }) => {
    const sidebar = page.locator("nav.hidden.md\\:flex");
    await expect(sidebar.locator("a", { hasText: "Dashboard" })).toBeVisible();
    await expect(page.locator("button", { hasText: "中文" })).toBeVisible();
  });

  test("toggle switches to Chinese", async ({ page }) => {
    await page.locator("button", { hasText: "中文" }).click();
    const sidebar = page.locator("nav.hidden.md\\:flex");
    await expect(sidebar.locator("a", { hasText: "儀表板" })).toBeVisible();
    await expect(page.locator("button", { hasText: "EN" })).toBeVisible();
  });

  test("toggle back switches to English", async ({ page }) => {
    await page.locator("button", { hasText: "中文" }).click();
    await expect(page.locator("button", { hasText: "EN" })).toBeVisible();
    await page.locator("button", { hasText: "EN" }).click();
    const sidebar = page.locator("nav.hidden.md\\:flex");
    await expect(sidebar.locator("a", { hasText: "Dashboard" })).toBeVisible();
  });

  test("locale persists across reload", async ({ page }) => {
    await page.locator("button", { hasText: "中文" }).click();
    await page.reload();
    await expect(page.locator("button", { hasText: "EN" })).toBeVisible();
  });
});
